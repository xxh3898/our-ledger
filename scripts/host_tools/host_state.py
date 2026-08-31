from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping


PROJECT = "our-ledger"
FORMAT_VERSION = 2
PRODUCTION_APP_ROOT = Path("/Users/homeserver/Server/apps/our-ledger")
MAX_RELEASE_FILE_SIZE = 2 * 1024 * 1024
MAX_RUNTIME_MANIFEST_SIZE = 64 * 1024
MAX_RUNTIME_MANIFEST_FILES = 256
RUNTIME_MANIFEST = "runtime-manifest.json"
FORBIDDEN_RELEASE_MARKERS = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN " + b"RSA PRIVATE KEY-----",
    b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----",
)

REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ZERO_REVISION = "0" * 40
DIGEST_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")
ZERO_DIGEST = "sha256:" + ("0" * 64)
STAGE_PATTERN = re.compile(r"^\.stage-([0-9a-f]{32})$")

LEGACY_RELEASE_FILES: Mapping[str, int] = {
    "compose.yaml": 0o600,
    "infra/nginx/nginx.conf": 0o600,
    "scripts/backup-production.sh": 0o700,
    "scripts/bootstrap-production.sh": 0o700,
    "scripts/backup_tools/backup_artifact.py": 0o600,
    "scripts/backup_tools/backup_core.sh": 0o600,
    "scripts/deploy-production.sh": 0o700,
    "scripts/host_tools/deploy_transaction.py": 0o600,
    "scripts/host_tools/fresh_bootstrap_state.py": 0o600,
    "scripts/host_tools/fresh_host_bootstrap.py": 0o600,
    "scripts/host_tools/host_state.py": 0o600,
    "scripts/host_tools/production_deploy.py": 0o600,
    "scripts/host_tools/production_fresh_bootstrap.py": 0o600,
    "scripts/host_tools/production_host.py": 0o600,
    "scripts/monitor-production.sh": 0o700,
    "scripts/production-status.sh": 0o700,
    "scripts/release_tools/release_contract.py": 0o700,
    "scripts/status_tools/monitor_policy.py": 0o600,
    "scripts/status_tools/monitor_worker.py": 0o600,
    "scripts/status_tools/production_status.py": 0o600,
}

LEGACY_RELEASE_DIRECTORIES = frozenset(
    str(parent)
    for relative in LEGACY_RELEASE_FILES
    for parent in PurePosixPath(relative).parents
    if str(parent) != "."
)

# Compatibility names remain available to the existing V1-only callers and tests.
RELEASE_FILES = LEGACY_RELEASE_FILES
RELEASE_DIRECTORIES = LEGACY_RELEASE_DIRECTORIES

MANIFEST_KEYS = frozenset({"formatVersion", "project", "files"})
MANIFEST_FILE_KEYS = frozenset({"path", "mode"})

STATE_KEYS = frozenset({"formatVersion", "project", "current", "previous"})
PENDING_KEYS = frozenset(
    {
        "formatVersion",
        "project",
        "phase",
        "candidate",
        "previous",
        "actor",
        "startedAt",
        "schemaBefore",
        "schemaAfter",
    }
)
IDENTITY_KEYS = frozenset(
    {
        "applicationRevision",
        "runtimeConfigDigest",
        "runtimeConfigRevision",
        "runtimeConfigContentSha256",
    }
)
SCHEMA_AUTHORITY_KEYS = frozenset(
    {"successfulVersion", "failedMigrationCount", "historySha256"}
)
DEPLOYMENT_PHASES = (
    "ARTIFACTS_VERIFIED",
    "WRITER_QUIESCED",
    "BACKUP_VERIFIED",
    "MIGRATION_STARTED",
    "MIGRATION_VERIFIED",
    "CUTOVER_STARTED",
    "READINESS_VERIFIED",
    "COMMITTING",
)
DEPLOYMENT_PHASE_TRANSITIONS = {
    current: following
    for current, following in zip(DEPLOYMENT_PHASES, DEPLOYMENT_PHASES[1:])
}
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
FLYWAY_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*(?:[.][0-9]+)*$")


class ContractError(RuntimeError):
    pass


class LockBusyError(ContractError):
    pass


@dataclass(frozen=True)
class RuntimeReleaseProfile:
    format_version: int
    files: tuple[tuple[str, int], ...]
    manifest_bytes: bytes | None = None

    @property
    def file_modes(self) -> dict[str, int]:
        return dict(self.files)

    @property
    def all_file_modes(self) -> dict[str, int]:
        if self.format_version == 1:
            return self.file_modes
        return {RUNTIME_MANIFEST: 0o600, **self.file_modes}

    @property
    def directories(self) -> frozenset[str]:
        return _directories_for(self.all_file_modes)


@dataclass(frozen=True)
class SchemaAuthority:
    successful_version: str
    failed_migration_count: int
    history_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.successful_version, str)
            or FLYWAY_VERSION_PATTERN.fullmatch(self.successful_version) is None
        ):
            raise ContractError("schema version authority is invalid")
        if (
            type(self.failed_migration_count) is not int
            or self.failed_migration_count != 0
        ):
            raise ContractError("failed migration authority is invalid")
        if (
            not isinstance(self.history_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.history_sha256) is None
        ):
            raise ContractError("schema history authority is invalid")

    def to_json(self) -> dict[str, object]:
        return {
            "successfulVersion": self.successful_version,
            "failedMigrationCount": self.failed_migration_count,
            "historySha256": self.history_sha256,
        }

    @classmethod
    def from_json(cls, value: object) -> "SchemaAuthority":
        if not isinstance(value, dict) or set(value) != SCHEMA_AUTHORITY_KEYS:
            raise ContractError("schema authority schema is invalid")
        return cls(
            successful_version=value["successfulVersion"],
            failed_migration_count=value["failedMigrationCount"],
            history_sha256=value["historySha256"],
        )


@dataclass(frozen=True)
class HostPaths:
    app_root: Path

    def __post_init__(self) -> None:
        if not self.app_root.is_absolute():
            raise ContractError("host root must be absolute")
        if self.app_root == Path("/") or len(self.app_root.parts) < 3:
            raise ContractError("host root is too broad")

    @property
    def runtime_root(self) -> Path:
        return self.app_root / "runtime-config"

    @property
    def releases(self) -> Path:
        return self.runtime_root / "releases"

    @property
    def state_dir(self) -> Path:
        return self.runtime_root / "state"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "deployment.json"

    @property
    def pending_dir(self) -> Path:
        return self.runtime_root / "pending"

    @property
    def pending_file(self) -> Path:
        return self.pending_dir / "transaction.json"

    @property
    def current(self) -> Path:
        return self.runtime_root / "current"

    @property
    def operations(self) -> Path:
        return self.app_root / "operations"

    @property
    def lock(self) -> Path:
        return self.operations / "lock"


@dataclass(frozen=True)
class ReleaseIdentity:
    application_revision: str
    runtime_config_digest: str
    runtime_config_revision: str
    runtime_config_content_sha256: str

    def __post_init__(self) -> None:
        _require_revision(self.application_revision)
        _require_digest(self.runtime_config_digest)
        _require_revision(self.runtime_config_revision)
        if not re.fullmatch(r"[0-9a-f]{64}", self.runtime_config_content_sha256):
            raise ContractError("runtime config content identity is invalid")

    @property
    def release_name(self) -> str:
        return _require_digest(self.runtime_config_digest)

    def to_json(self) -> dict[str, str]:
        return {
            "applicationRevision": self.application_revision,
            "runtimeConfigDigest": self.runtime_config_digest,
            "runtimeConfigRevision": self.runtime_config_revision,
            "runtimeConfigContentSha256": self.runtime_config_content_sha256,
        }

    @classmethod
    def from_json(cls, value: object) -> "ReleaseIdentity":
        if not isinstance(value, dict) or set(value) != IDENTITY_KEYS:
            raise ContractError("deployment identity schema is invalid")
        if not all(isinstance(item, str) for item in value.values()):
            raise ContractError("deployment identity values are invalid")
        return cls(
            application_revision=value["applicationRevision"],
            runtime_config_digest=value["runtimeConfigDigest"],
            runtime_config_revision=value["runtimeConfigRevision"],
            runtime_config_content_sha256=value["runtimeConfigContentSha256"],
        )


def legacy_release_profile() -> RuntimeReleaseProfile:
    return RuntimeReleaseProfile(
        format_version=1,
        files=tuple(LEGACY_RELEASE_FILES.items()),
    )


def parse_runtime_manifest(payload: bytes) -> RuntimeReleaseProfile:
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_RUNTIME_MANIFEST_SIZE:
        raise ContractError("runtime config manifest size is invalid")
    if any(marker in payload for marker in FORBIDDEN_RELEASE_MARKERS):
        raise ContractError("runtime config contains private key material")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("runtime config manifest is invalid") from error
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        raise ContractError("runtime config manifest schema is invalid")
    if type(value["formatVersion"]) is not int or value["formatVersion"] != 2:
        raise ContractError("runtime config manifest version is invalid")
    if value["project"] != PROJECT:
        raise ContractError("runtime config manifest project is invalid")
    file_values = value["files"]
    if (
        not isinstance(file_values, list)
        or not file_values
        or len(file_values) > MAX_RUNTIME_MANIFEST_FILES
    ):
        raise ContractError("runtime config manifest files are invalid")

    files: list[tuple[str, int]] = []
    for file_value in file_values:
        if not isinstance(file_value, dict) or set(file_value) != MANIFEST_FILE_KEYS:
            raise ContractError("runtime config manifest file schema is invalid")
        relative = _require_manifest_path(file_value["path"])
        mode_value = file_value["mode"]
        if not isinstance(mode_value, str) or mode_value not in {"0600", "0700"}:
            raise ContractError("runtime config manifest file mode is invalid")
        files.append((relative, int(mode_value, 8)))

    paths = [relative for relative, _ in files]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ContractError("runtime config manifest paths are not sorted and unique")
    return RuntimeReleaseProfile(
        format_version=2,
        files=tuple(files),
        manifest_bytes=payload,
    )


def production_paths() -> HostPaths:
    return HostPaths(PRODUCTION_APP_ROOT)


def initialize_layout(paths: HostPaths) -> None:
    """Create only the owner-only B1 host layout below an injected root."""
    _create_or_validate_directory(paths.app_root, create=True)
    for directory in (
        paths.runtime_root,
        paths.releases,
        paths.state_dir,
        paths.pending_dir,
        paths.operations,
    ):
        _create_or_validate_directory(directory, create=True)
    _fsync_directory(paths.app_root)
    _validate_layout_entries(paths)


def validate_layout(paths: HostPaths) -> None:
    for directory in (
        paths.app_root,
        paths.runtime_root,
        paths.releases,
        paths.state_dir,
        paths.pending_dir,
        paths.operations,
    ):
        _create_or_validate_directory(directory, create=False)
    _validate_layout_entries(paths)


class OperationLock:
    """Non-blocking, non-stealing project lock based on atomic mkdir."""

    def __init__(self, paths: HostPaths):
        self.paths = paths
        self._identity: tuple[int, int] | None = None

    def __enter__(self) -> "OperationLock":
        validate_layout(self.paths)
        try:
            os.mkdir(self.paths.lock, 0o700)
        except FileExistsError as error:
            raise LockBusyError("project operation lock is already held") from error
        except OSError as error:
            raise ContractError("project operation lock could not be created") from error

        try:
            lock_stat = _require_directory(self.paths.lock, 0o700)
            _require_directory_empty(self.paths.lock)
            self._identity = (lock_stat.st_dev, lock_stat.st_ino)
            _fsync_directory(self.paths.operations)
            return self
        except BaseException:
            try:
                os.rmdir(self.paths.lock)
                _fsync_directory(self.paths.operations)
            except OSError:
                pass
            raise

    def assert_held(self, paths: HostPaths) -> None:
        if paths != self.paths or self._identity is None:
            raise ContractError("project operation lock is required")
        lock_stat = _require_directory(self.paths.lock, 0o700)
        if (lock_stat.st_dev, lock_stat.st_ino) != self._identity:
            raise ContractError("project operation lock identity changed")
        _require_directory_empty(self.paths.lock)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._identity is None:
            return False
        self.assert_held(self.paths)
        try:
            os.rmdir(self.paths.lock)
            _fsync_directory(self.paths.operations)
        except OSError as error:
            raise ContractError("project operation lock could not be released") from error
        finally:
            self._identity = None
        return False


def stage_release(
    paths: HostPaths,
    lock: OperationLock,
    source_root: Path,
    *,
    application_revision: str,
    runtime_config_digest: str,
    runtime_config_revision: str,
) -> ReleaseIdentity:
    lock.assert_held(paths)
    _require_no_pending(paths)
    _require_stable_committed_state(paths)
    if _abandoned_stages(paths):
        raise ContractError("runtime config staging recovery is required")
    source_root = _require_release_root(source_root)
    source_profile = _validate_release(source_root)
    if source_root.is_relative_to(paths.app_root) or paths.app_root.is_relative_to(
        source_root
    ):
        raise ContractError("runtime config source and host root must be disjoint")
    source_content = _release_content_sha256(source_root, source_profile)
    identity = ReleaseIdentity(
        application_revision=application_revision,
        runtime_config_digest=runtime_config_digest,
        runtime_config_revision=runtime_config_revision,
        runtime_config_content_sha256=source_content,
    )
    destination = paths.releases / identity.release_name

    if os.path.lexists(destination):
        _validate_release(destination)
        if release_content_sha256(destination) != source_content:
            raise ContractError("immutable runtime config release differs")
        return identity

    stage = paths.releases / f".stage-{uuid.uuid4().hex}"
    try:
        os.mkdir(stage, 0o700)
        if source_profile.format_version == 2:
            _copy_regular_file(
                source_root / RUNTIME_MANIFEST,
                stage / RUNTIME_MANIFEST,
                0o600,
            )
        for relative in sorted(
            source_profile.directories,
            key=lambda item: item.count("/"),
        ):
            os.mkdir(stage / relative, 0o700)
        for relative, mode in source_profile.files:
            _copy_regular_file(source_root / relative, stage / relative, mode)
        _fsync_release_directories(stage, source_profile.directories)
        staged_profile = _validate_release(stage)
        final_source_profile = _validate_release(source_root)
        if (
            staged_profile != source_profile
            or final_source_profile != source_profile
            or _release_content_sha256(stage, staged_profile) != source_content
            or _release_content_sha256(source_root, final_source_profile)
            != source_content
        ):
            raise ContractError("runtime config source changed during staging")
        os.rename(stage, destination)
        _fsync_directory(paths.releases)
    except BaseException:
        if os.path.lexists(stage):
            _remove_owned_stage(stage, source_profile)
            _fsync_directory(paths.releases)
        raise

    _validate_release(destination)
    return identity


def release_content_sha256(release_root: Path) -> str:
    profile = _validate_release(release_root)
    return _release_content_sha256(release_root, profile)


def _release_content_sha256(
    release_root: Path,
    profile: RuntimeReleaseProfile,
) -> str:
    digest = hashlib.sha256()
    if profile.format_version == 2:
        assert profile.manifest_bytes is not None
        digest.update(b"our-ledger-runtime-config\0manifest-v2\0")
        digest.update(RUNTIME_MANIFEST.encode("ascii"))
        digest.update(b"\0")
        digest.update(b"0600\0")
        digest.update(profile.manifest_bytes)
        digest.update(b"\0")
    for relative, mode in profile.files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{mode:04o}".encode("ascii"))
        digest.update(b"\0")
        with _open_regular_nofollow(release_root / relative, mode) as source:
            marker_tail = b""
            while chunk := source.read(1024 * 1024):
                marker_window = marker_tail + chunk
                if any(marker in marker_window for marker in FORBIDDEN_RELEASE_MARKERS):
                    raise ContractError("runtime config contains private key material")
                digest.update(chunk)
                marker_tail = marker_window[-64:]
        digest.update(b"\0")
    return digest.hexdigest()


def begin_pending(
    paths: HostPaths,
    lock: OperationLock,
    candidate: ReleaseIdentity,
) -> None:
    lock.assert_held(paths)
    _require_no_pending(paths)
    _require_stable_committed_state(paths)
    _require_identity_release(paths, candidate)
    previous = _read_committed_identity(paths)
    payload = {
        "formatVersion": FORMAT_VERSION,
        "project": PROJECT,
        "phase": "STAGED",
        "candidate": candidate.to_json(),
        "previous": previous.to_json() if previous else None,
        "actor": None,
        "startedAt": None,
        "schemaBefore": None,
        "schemaAfter": None,
    }
    _atomic_write_json(paths.pending_file, payload)


def begin_deployment_pending(
    paths: HostPaths,
    lock: OperationLock,
    candidate: ReleaseIdentity,
    *,
    actor: str,
    started_at: str,
) -> None:
    lock.assert_held(paths)
    _require_no_pending(paths)
    _require_stable_committed_state(paths)
    _require_identity_release(paths, candidate)
    previous = _read_committed_identity(paths)
    payload = {
        "formatVersion": FORMAT_VERSION,
        "project": PROJECT,
        "phase": DEPLOYMENT_PHASES[0],
        "candidate": candidate.to_json(),
        "previous": previous.to_json() if previous else None,
        "actor": _require_actor(actor),
        "startedAt": _require_instant(started_at),
        "schemaBefore": None,
        "schemaAfter": None,
    }
    _atomic_write_json(paths.pending_file, payload)


def advance_deployment_pending(
    paths: HostPaths,
    lock: OperationLock,
    *,
    expected_phase: str,
    next_phase: str,
    schema_before: SchemaAuthority | None = None,
    schema_after: SchemaAuthority | None = None,
) -> None:
    lock.assert_held(paths)
    pending = _read_pending(paths, required=True)
    if pending["phase"] != expected_phase:
        raise ContractError("deployment pending phase differs")
    if DEPLOYMENT_PHASE_TRANSITIONS.get(expected_phase) != next_phase:
        raise ContractError("deployment pending phase transition is invalid")

    current_before = pending["schemaBefore"]
    current_after = pending["schemaAfter"]
    if schema_before is not None:
        if current_before is not None and current_before != schema_before:
            raise ContractError("deployment pre-migration schema authority differs")
        current_before = schema_before
    if schema_after is not None:
        if current_after is not None and current_after != schema_after:
            raise ContractError("deployment post-migration schema authority differs")
        current_after = schema_after
    if next_phase in DEPLOYMENT_PHASES[2:] and current_before is None:
        raise ContractError("deployment pre-migration schema authority is missing")
    if next_phase in DEPLOYMENT_PHASES[4:] and current_after is None:
        raise ContractError("deployment post-migration schema authority is missing")

    _write_pending(
        paths,
        pending,
        phase=next_phase,
        schema_before=current_before,
        schema_after=current_after,
    )


def deployment_pending(
    paths: HostPaths,
    lock: OperationLock,
) -> dict[str, object] | None:
    lock.assert_held(paths)
    pending = _read_pending(paths, required=False)
    if pending is None:
        return None
    return {
        "phase": pending["phase"],
        "candidate": pending["candidate"],
        "previous": pending["previous"],
        "actor": pending["actor"],
        "startedAt": pending["startedAt"],
        "schemaBefore": pending["schemaBefore"],
        "schemaAfter": pending["schemaAfter"],
    }


def commit_pending(
    paths: HostPaths,
    lock: OperationLock,
    *,
    after_current: Callable[[], None] | None = None,
    after_state: Callable[[], None] | None = None,
) -> ReleaseIdentity:
    lock.assert_held(paths)
    pending = _read_pending(paths, required=True)
    phase = pending["phase"]
    if phase == "READINESS_VERIFIED":
        _write_pending(
            paths,
            pending,
            phase="COMMITTING",
            schema_before=pending["schemaBefore"],
            schema_after=pending["schemaAfter"],
        )
        pending = _read_pending(paths, required=True)
    elif phase != "STAGED":
        raise ContractError("pending transaction is not ready to commit")
    candidate = pending["candidate"]
    assert isinstance(candidate, ReleaseIdentity)
    previous = pending["previous"]
    if (
        _read_committed_identity(paths) != previous
        or _read_current_identity(paths) != previous
    ):
        raise ContractError("pending predecessor no longer matches committed state")
    _require_identity_release(paths, candidate)
    _write_current(paths, candidate)
    if after_current is not None:
        after_current()
    state = {
        "formatVersion": FORMAT_VERSION,
        "project": PROJECT,
        "current": candidate.to_json(),
        "previous": (
            previous.to_json()
            if isinstance(previous, ReleaseIdentity)
            else None
        ),
    }
    _atomic_write_json(paths.state_file, state)
    if after_state is not None:
        after_state()
    _unlink_regular_file(paths.pending_file, 0o600)
    return candidate


def finish_committed_pending(
    paths: HostPaths,
    lock: OperationLock,
) -> ReleaseIdentity:
    lock.assert_held(paths)
    pending = _read_pending(paths, required=True)
    if pending["phase"] != "COMMITTING":
        raise ContractError("deployment pending is not committing")
    candidate = pending["candidate"]
    assert isinstance(candidate, ReleaseIdentity)
    previous = pending["previous"]
    committed = _read_committed_identity(paths)
    current = _read_current_identity(paths)
    if committed not in (previous, candidate) or current not in (previous, candidate):
        raise ContractError("committing deployment is not durably current")
    if current != candidate:
        _write_current(paths, candidate)
    if committed != candidate:
        state = {
            "formatVersion": FORMAT_VERSION,
            "project": PROJECT,
            "current": candidate.to_json(),
            "previous": previous.to_json() if previous else None,
        }
        _atomic_write_json(paths.state_file, state)
    _unlink_regular_file(paths.pending_file, 0o600)
    return candidate


def clear_abandoned_pending(paths: HostPaths, lock: OperationLock) -> None:
    lock.assert_held(paths)
    pending = _read_pending(paths, required=True)
    if pending["phase"] not in {
        "STAGED",
        "ARTIFACTS_VERIFIED",
        "WRITER_QUIESCED",
        "BACKUP_VERIFIED",
    }:
        raise ContractError("pending transaction is not safe to abandon")
    previous = pending["previous"]
    committed = _read_committed_identity(paths)
    current = _read_current_identity(paths)
    if committed != previous or current != previous:
        raise ContractError("pending transaction is not safe to abandon")
    _unlink_regular_file(paths.pending_file, 0o600)


def clear_recovered_deployment_pending(
    paths: HostPaths,
    lock: OperationLock,
) -> None:
    """Clear only after the caller verified schema and restored the predecessor."""
    lock.assert_held(paths)
    pending = _read_pending(paths, required=True)
    if pending["phase"] not in DEPLOYMENT_PHASES:
        raise ContractError("recovered pending is not a deployment transaction")
    previous = pending["previous"]
    if (
        _read_committed_identity(paths) != previous
        or _read_current_identity(paths) != previous
    ):
        raise ContractError("recovered deployment predecessor is not current")
    _unlink_regular_file(paths.pending_file, 0o600)


def inspect_state(paths: HostPaths, lock: OperationLock) -> dict[str, object]:
    lock.assert_held(paths)
    committed = _read_committed_identity(paths)
    current = _read_current_identity(paths)
    pending = _read_pending(paths, required=False)
    stages = _abandoned_stages(paths)

    if pending is None:
        if committed != current:
            raise ContractError("runtime config state and current pointer differ")
    else:
        previous = pending["previous"]
        candidate = pending["candidate"]
        valid_transition = (
            committed == previous and current in (previous, candidate)
        ) or (committed == candidate and current == candidate)
        if not valid_transition:
            raise ContractError("runtime config pending transition is inconsistent")
    status = "PENDING" if pending is not None else ("READY" if current else "FRESH")
    return {
        "formatVersion": FORMAT_VERSION,
        "project": PROJECT,
        "status": status,
        "current": current.to_json() if current else None,
        "pending": pending is not None,
        "abandonedStages": stages,
    }


def clear_abandoned_stage(
    paths: HostPaths,
    lock: OperationLock,
    stage_name: str,
) -> None:
    lock.assert_held(paths)
    if not STAGE_PATTERN.fullmatch(stage_name):
        raise ContractError("runtime config stage name is invalid")
    stage = paths.releases / stage_name
    _remove_owned_stage(stage)
    _fsync_directory(paths.releases)


def _validate_layout_entries(paths: HostPaths) -> None:
    _require_allowed_entries(paths.runtime_root, {"releases", "state", "pending", "current"})
    _require_allowed_entries(paths.state_dir, {"deployment.json"})
    _require_allowed_entries(paths.pending_dir, {"transaction.json"})
    _require_allowed_entries(paths.operations, {"lock"})

    for entry in os.scandir(paths.releases):
        if re.fullmatch(r"[0-9a-f]{64}", entry.name):
            _validate_release(Path(entry.path))
        elif STAGE_PATTERN.fullmatch(entry.name):
            _validate_partial_stage(Path(entry.path))
        else:
            raise ContractError("runtime config releases contain an unexpected entry")

    if os.path.lexists(paths.state_file):
        _require_regular_file(paths.state_file, 0o600)
    if os.path.lexists(paths.pending_file):
        _require_regular_file(paths.pending_file, 0o600)
    if os.path.lexists(paths.current):
        _require_current_link(paths)
    if os.path.lexists(paths.lock):
        _require_directory(paths.lock, 0o700)
        _require_directory_empty(paths.lock)


def _validate_release(root: Path) -> RuntimeReleaseProfile:
    if os.path.lexists(root / RUNTIME_MANIFEST):
        profile = parse_runtime_manifest(_read_runtime_manifest(root / RUNTIME_MANIFEST))
    else:
        profile = legacy_release_profile()
    _validate_release_profile(root, profile)
    return profile


def _validate_release_profile(root: Path, profile: RuntimeReleaseProfile) -> None:
    _require_directory(root, 0o700)
    actual_directories: set[str] = set()
    actual_files: set[str] = set()
    expected_files = profile.all_file_modes
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(root)
        if relative_current != Path("."):
            _require_directory(current_path, 0o700)
            actual_directories.add(relative_current.as_posix())
        for name in directories:
            candidate = current_path / name
            candidate_stat = os.lstat(candidate)
            if not stat.S_ISDIR(candidate_stat.st_mode):
                raise ContractError("runtime config release contains a non-directory")
        for name in files:
            candidate = current_path / name
            relative = candidate.relative_to(root).as_posix()
            expected_mode = expected_files.get(relative)
            if expected_mode is None:
                raise ContractError("runtime config release contains an unexpected file")
            candidate_stat = _require_regular_file(candidate, expected_mode)
            size_limit = (
                MAX_RUNTIME_MANIFEST_SIZE
                if relative == RUNTIME_MANIFEST
                else MAX_RELEASE_FILE_SIZE
            )
            if candidate_stat.st_size > size_limit:
                raise ContractError("runtime config file is too large")
            actual_files.add(relative)
    if actual_directories != profile.directories or actual_files != set(expected_files):
        raise ContractError("runtime config release allowlist differs")


def _read_runtime_manifest(path: Path) -> bytes:
    path_stat = _require_regular_file(path, 0o600)
    if path_stat.st_size <= 0 or path_stat.st_size > MAX_RUNTIME_MANIFEST_SIZE:
        raise ContractError("runtime config manifest size is invalid")
    try:
        with _open_regular_nofollow(path, 0o600) as source:
            payload = source.read(MAX_RUNTIME_MANIFEST_SIZE + 1)
    except OSError as error:
        raise ContractError("runtime config manifest is unavailable") from error
    if len(payload) != path_stat.st_size:
        raise ContractError("runtime config manifest changed during read")
    return payload


def _require_release_root(root: Path) -> Path:
    if not root.is_absolute():
        raise ContractError("runtime config source root must be absolute")
    try:
        if root.resolve(strict=True) != root:
            raise ContractError("runtime config source root is not canonical")
    except OSError as error:
        raise ContractError("runtime config source root is unavailable") from error
    _validate_release(root)
    return root


def _copy_regular_file(source: Path, destination: Path, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    destination_fd: int | None = None
    try:
        with _open_regular_nofollow(source, mode) as source_file:
            destination_fd = os.open(destination, flags, mode)
            os.fchmod(destination_fd, mode)
            with os.fdopen(destination_fd, "wb", closefd=False) as destination_file:
                while chunk := source_file.read(1024 * 1024):
                    destination_file.write(chunk)
                destination_file.flush()
            os.fsync(destination_fd)
    except OSError as error:
        raise ContractError("runtime config file copy failed") from error
    finally:
        if destination_fd is not None:
            os.close(destination_fd)


def _open_regular_nofollow(path: Path, expected_mode: int):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ContractError("runtime config file could not be opened") from error
    try:
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.lstat(path)
        if not stat.S_ISREG(descriptor_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise ContractError("runtime config entry is not a regular file")
        if (descriptor_stat.st_dev, descriptor_stat.st_ino) != (
            path_stat.st_dev,
            path_stat.st_ino,
        ):
            raise ContractError("runtime config file identity changed")
        _require_owner_mode(descriptor_stat, expected_mode)
        if descriptor_stat.st_nlink != 1:
            raise ContractError("runtime config hardlink is not allowed")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _require_identity_release(paths: HostPaths, identity: ReleaseIdentity) -> None:
    release = paths.releases / identity.release_name
    _validate_release(release)
    if release_content_sha256(release) != identity.runtime_config_content_sha256:
        raise ContractError("runtime config release identity differs")


def _read_committed_identity(paths: HostPaths) -> ReleaseIdentity | None:
    if not os.path.lexists(paths.state_file):
        return None
    value = _read_json(paths.state_file, STATE_KEYS)
    if (
        type(value["formatVersion"]) is not int
        or value["formatVersion"] != FORMAT_VERSION
        or value["project"] != PROJECT
    ):
        raise ContractError("runtime config state authority is invalid")
    current_value = value["current"]
    previous_value = value["previous"]
    current = ReleaseIdentity.from_json(current_value) if current_value is not None else None
    previous = (
        ReleaseIdentity.from_json(previous_value)
        if previous_value is not None
        else None
    )
    if current is None:
        raise ContractError("runtime config state current identity is missing")
    _require_identity_release(paths, current)
    if previous is not None:
        _require_identity_release(paths, previous)
    return current


def _require_stable_committed_state(paths: HostPaths) -> None:
    committed = _read_committed_identity(paths)
    current = _read_current_identity(paths)
    if committed != current:
        raise ContractError("runtime config state and current pointer differ")


def _read_pending(paths: HostPaths, *, required: bool) -> dict[str, object] | None:
    if not os.path.lexists(paths.pending_file):
        if required:
            raise ContractError("runtime config pending transaction is missing")
        return None
    value = _read_json(paths.pending_file, PENDING_KEYS)
    if (
        type(value["formatVersion"]) is not int
        or value["formatVersion"] != FORMAT_VERSION
        or value["project"] != PROJECT
        or value["phase"] not in {"STAGED", *DEPLOYMENT_PHASES}
    ):
        raise ContractError("runtime config pending authority is invalid")
    candidate = ReleaseIdentity.from_json(value["candidate"])
    previous = (
        ReleaseIdentity.from_json(value["previous"])
        if value["previous"] is not None
        else None
    )
    phase = value["phase"]
    actor = value["actor"]
    started_at = value["startedAt"]
    schema_before = (
        SchemaAuthority.from_json(value["schemaBefore"])
        if value["schemaBefore"] is not None
        else None
    )
    schema_after = (
        SchemaAuthority.from_json(value["schemaAfter"])
        if value["schemaAfter"] is not None
        else None
    )
    if phase == "STAGED":
        if any(
            item is not None
            for item in (actor, started_at, schema_before, schema_after)
        ):
            raise ContractError("runtime config staged pending authority is invalid")
    else:
        _require_actor(actor)
        _require_instant(started_at)
        phase_index = DEPLOYMENT_PHASES.index(phase)
        if (phase_index >= 2) != (schema_before is not None):
            raise ContractError("deployment pre-migration schema authority differs")
        if (phase_index >= 4) != (schema_after is not None):
            raise ContractError("deployment post-migration schema authority differs")
    _require_identity_release(paths, candidate)
    if previous is not None:
        _require_identity_release(paths, previous)
    return {
        "phase": phase,
        "candidate": candidate,
        "previous": previous,
        "actor": actor,
        "startedAt": started_at,
        "schemaBefore": schema_before,
        "schemaAfter": schema_after,
    }


def _write_pending(
    paths: HostPaths,
    pending: dict[str, object],
    *,
    phase: str,
    schema_before: SchemaAuthority | None,
    schema_after: SchemaAuthority | None,
) -> None:
    candidate = pending["candidate"]
    previous = pending["previous"]
    if not isinstance(candidate, ReleaseIdentity):
        raise ContractError("deployment candidate identity is invalid")
    if previous is not None and not isinstance(previous, ReleaseIdentity):
        raise ContractError("deployment previous identity is invalid")
    payload = {
        "formatVersion": FORMAT_VERSION,
        "project": PROJECT,
        "phase": phase,
        "candidate": candidate.to_json(),
        "previous": previous.to_json() if previous else None,
        "actor": pending["actor"],
        "startedAt": pending["startedAt"],
        "schemaBefore": schema_before.to_json() if schema_before else None,
        "schemaAfter": schema_after.to_json() if schema_after else None,
    }
    _atomic_write_json(paths.pending_file, payload)


def _read_current_identity(paths: HostPaths) -> ReleaseIdentity | None:
    if not os.path.lexists(paths.current):
        return None
    release_name = _require_current_link(paths)
    release = paths.releases / release_name
    _validate_release(release)
    content_hash = release_content_sha256(release)
    state = _read_committed_identity(paths)
    pending = _read_pending(paths, required=False)
    candidates = [state]
    if pending is not None:
        candidates.extend([pending["candidate"], pending["previous"]])
    for identity in candidates:
        if (
            isinstance(identity, ReleaseIdentity)
            and identity.release_name == release_name
            and identity.runtime_config_content_sha256 == content_hash
        ):
            return identity
    raise ContractError("current pointer has no verified identity")


def _write_current(paths: HostPaths, identity: ReleaseIdentity) -> None:
    _require_identity_release(paths, identity)
    target = f"releases/{identity.release_name}"
    temporary = paths.runtime_root / f".current-{uuid.uuid4().hex}"
    try:
        os.symlink(target, temporary)
        os.replace(temporary, paths.current)
        _fsync_directory(paths.runtime_root)
    except OSError as error:
        raise ContractError("runtime config current pointer update failed") from error
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _require_current_link(paths: HostPaths) -> str:
    current_stat = os.lstat(paths.current)
    if not stat.S_ISLNK(current_stat.st_mode):
        raise ContractError("runtime config current pointer is not a symlink")
    target = os.readlink(paths.current)
    match = re.fullmatch(r"releases/([0-9a-f]{64})", target)
    if match is None:
        raise ContractError("runtime config current pointer target is invalid")
    return match.group(1)


def _require_no_pending(paths: HostPaths) -> None:
    if os.path.lexists(paths.pending_file):
        _read_pending(paths, required=True)
        raise ContractError("runtime config transaction is already pending")


def _atomic_write_json(path: Path, value: object) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    if len(payload) > 16 * 1024:
        raise ContractError("host state payload is too large")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as error:
        raise ContractError("host state atomic write failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _read_json(path: Path, expected_keys: frozenset[str]) -> dict[str, object]:
    path_stat = _require_regular_file(path, 0o600)
    if path_stat.st_size > 16 * 1024:
        raise ContractError("host state payload is too large")
    try:
        with _open_regular_nofollow(path, 0o600) as source:
            value = json.load(source, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("host state payload is invalid") from error
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ContractError("host state schema is invalid")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("host state contains duplicate keys")
        result[key] = value
    return result


def _unlink_regular_file(path: Path, mode: int) -> None:
    _require_regular_file(path, mode)
    try:
        os.unlink(path)
        _fsync_directory(path.parent)
    except OSError as error:
        raise ContractError("host state file removal failed") from error


def _abandoned_stages(paths: HostPaths) -> list[str]:
    stages = []
    for entry in os.scandir(paths.releases):
        if STAGE_PATTERN.fullmatch(entry.name):
            _validate_partial_stage(Path(entry.path))
            stages.append(entry.name)
    return sorted(stages)


def _remove_owned_stage(
    stage: Path,
    profile: RuntimeReleaseProfile | None = None,
) -> None:
    if not STAGE_PATTERN.fullmatch(stage.name):
        raise ContractError("runtime config stage path is invalid")
    _validate_partial_stage(stage, profile)
    for current, directories, files in os.walk(stage, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in files:
            os.unlink(current_path / name)
        for name in directories:
            os.rmdir(current_path / name)
    os.rmdir(stage)


def _validate_partial_stage(
    root: Path,
    profile: RuntimeReleaseProfile | None = None,
) -> None:
    _require_directory(root, 0o700)
    if profile is None:
        if os.path.lexists(root / RUNTIME_MANIFEST):
            try:
                profile = parse_runtime_manifest(
                    _read_runtime_manifest(root / RUNTIME_MANIFEST)
                )
            except ContractError:
                profile = RuntimeReleaseProfile(
                    format_version=2,
                    files=(),
                    manifest_bytes=b"",
                )
        else:
            profile = legacy_release_profile()
    expected_files = profile.all_file_modes
    actual_directories: set[str] = set()
    actual_files: set[str] = set()
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(root)
        if relative_current != Path("."):
            _require_directory(current_path, 0o700)
            actual_directories.add(relative_current.as_posix())
        for name in directories:
            candidate = current_path / name
            candidate_stat = os.lstat(candidate)
            if not stat.S_ISDIR(candidate_stat.st_mode):
                raise ContractError("runtime config stage contains a non-directory")
        for name in files:
            candidate = current_path / name
            relative = candidate.relative_to(root).as_posix()
            expected_mode = expected_files.get(relative)
            if expected_mode is None:
                raise ContractError("runtime config stage contains an unexpected file")
            candidate_stat = _require_regular_file(candidate, expected_mode)
            size_limit = (
                MAX_RUNTIME_MANIFEST_SIZE
                if relative == RUNTIME_MANIFEST
                else MAX_RELEASE_FILE_SIZE
            )
            if candidate_stat.st_size > size_limit:
                raise ContractError("runtime config stage file is too large")
            actual_files.add(relative)
    if not actual_directories.issubset(profile.directories):
        raise ContractError("runtime config stage directory allowlist differs")
    if not actual_files.issubset(expected_files):
        raise ContractError("runtime config stage file allowlist differs")


def _fsync_release_directories(
    root: Path,
    directories: frozenset[str],
) -> None:
    for relative in sorted(
        directories,
        key=lambda item: item.count("/"),
        reverse=True,
    ):
        _fsync_directory(root / relative)
    _fsync_directory(root)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ContractError("directory durability barrier failed") from error


def _create_or_validate_directory(path: Path, *, create: bool) -> None:
    if not os.path.lexists(path):
        if not create:
            raise ContractError("required host directory is missing")
        try:
            if path.parent.resolve(strict=True) != path.parent:
                raise ContractError("host directory parent is not canonical")
        except OSError as error:
            raise ContractError("host directory parent is unavailable") from error
        try:
            os.mkdir(path, 0o700)
        except OSError as error:
            raise ContractError("owner-only host directory could not be created") from error
        _fsync_directory(path.parent)
    _require_directory(path, 0o700)


def _require_directory(path: Path, mode: int) -> os.stat_result:
    try:
        path_stat = os.lstat(path)
    except OSError as error:
        raise ContractError("required directory is unavailable") from error
    if not stat.S_ISDIR(path_stat.st_mode):
        raise ContractError("host path is not a directory")
    try:
        if path.resolve(strict=True) != path:
            raise ContractError("host directory path is not canonical")
    except OSError as error:
        raise ContractError("host directory path is unavailable") from error
    _require_owner_mode(path_stat, mode)
    return path_stat


def _require_regular_file(path: Path, mode: int) -> os.stat_result:
    try:
        path_stat = os.lstat(path)
    except OSError as error:
        raise ContractError("required file is unavailable") from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise ContractError("host path is not a regular file")
    try:
        if path.resolve(strict=True) != path:
            raise ContractError("host file path is not canonical")
    except OSError as error:
        raise ContractError("host file path is unavailable") from error
    _require_owner_mode(path_stat, mode)
    if path_stat.st_nlink != 1:
        raise ContractError("host hardlink is not allowed")
    return path_stat


def _require_owner_mode(path_stat: os.stat_result, mode: int) -> None:
    if path_stat.st_uid != os.getuid() or stat.S_IMODE(path_stat.st_mode) != mode:
        raise ContractError("host path owner or mode is invalid")


def _require_directory_empty(path: Path) -> None:
    try:
        with os.scandir(path) as entries:
            if next(entries, None) is not None:
                raise ContractError("operation lock contains an unexpected entry")
    except OSError as error:
        raise ContractError("operation lock cannot be inspected") from error


def _require_allowed_entries(directory: Path, allowed: set[str]) -> None:
    actual = {entry.name for entry in os.scandir(directory)}
    unexpected = actual - allowed
    if unexpected:
        raise ContractError("managed host directory contains an unexpected entry")


def _directories_for(files: Mapping[str, int]) -> frozenset[str]:
    return frozenset(
        str(parent)
        for relative in files
        for parent in PurePosixPath(relative).parents
        if str(parent) != "."
    )


def _require_manifest_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\\" in value
        or value == RUNTIME_MANIFEST
    ):
        raise ContractError("runtime config manifest path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
        or not (
            value == "compose.yaml"
            or value.startswith("infra/")
            or value.startswith("scripts/")
        )
    ):
        raise ContractError("runtime config manifest path is invalid")
    return value


def _require_revision(value: str) -> str:
    if REVISION_PATTERN.fullmatch(value) is None or value == ZERO_REVISION:
        raise ContractError("application revision is invalid")
    return value


def _require_digest(value: str) -> str:
    match = DIGEST_PATTERN.fullmatch(value)
    if match is None or value == ZERO_DIGEST:
        raise ContractError("runtime config digest is invalid")
    return match.group(1)


def _require_actor(value: object) -> str:
    if not isinstance(value, str) or ACTOR_PATTERN.fullmatch(value) is None:
        raise ContractError("deployment actor is invalid")
    return value


def _require_instant(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ContractError("deployment timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("deployment timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ContractError("deployment timestamp is invalid")
    return value
