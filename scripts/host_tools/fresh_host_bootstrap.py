from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from scripts.host_tools import fresh_bootstrap_state, host_state
from scripts.host_tools.deploy_transaction import (
    API_REPOSITORY,
    RUNTIME_CONFIG_REPOSITORY,
    WEB_REPOSITORY,
)
from scripts.host_tools.host_state import (
    ContractError,
    HostPaths,
    OperationLock,
    ReleaseIdentity,
    SchemaAuthority,
)
from scripts.release_tools import release_contract


EXPECTED_SCHEMA_VERSION = "8"


class FreshBootstrapError(ContractError):
    pass


class FreshBootstrapInterventionRequired(FreshBootstrapError):
    pass


@dataclass(frozen=True)
class FreshBootstrapRequest:
    revision: str
    runtime_config_digest: str
    actor: str

    @classmethod
    def from_command(cls, value: str) -> "FreshBootstrapRequest":
        try:
            parsed = release_contract.parse_bootstrap_command(value)
        except release_contract.ContractError as error:
            raise FreshBootstrapError("restricted bootstrap command is invalid") from error
        return cls(
            revision=parsed["revision"],
            runtime_config_digest=parsed["runtimeConfigDigest"],
            actor=parsed["actor"],
        )


@dataclass(frozen=True)
class FreshCandidateArtifacts:
    revision: str
    api_reference: str
    web_reference: str
    runtime_config_digest: str
    runtime_config_revision: str
    runtime_source: Path

    def validate_for(self, request: FreshBootstrapRequest) -> None:
        if self.revision != request.revision:
            raise FreshBootstrapError("fresh candidate revision differs")
        if self.api_reference != f"{API_REPOSITORY}:{request.revision}":
            raise FreshBootstrapError("fresh candidate API authority differs")
        if self.web_reference != f"{WEB_REPOSITORY}:{request.revision}":
            raise FreshBootstrapError("fresh candidate Web authority differs")
        if (
            self.runtime_config_digest != request.runtime_config_digest
            or self.runtime_config_revision != request.revision
            or not self.runtime_source.is_absolute()
        ):
            raise FreshBootstrapError("fresh candidate runtime authority differs")


class FreshBootstrapAdapter(Protocol):
    def validate_authority(self) -> None: ...

    def validate_resource_authority(self, *, recovering: bool) -> None: ...

    def prepare_artifacts(
        self,
        request: FreshBootstrapRequest,
        token: bytearray,
    ) -> FreshCandidateArtifacts: ...

    def start_postgres(self, candidate: FreshCandidateArtifacts) -> None: ...

    def postgres_is_ready(self, candidate: FreshCandidateArtifacts) -> bool: ...

    def run_migration(self, candidate: FreshCandidateArtifacts) -> None: ...

    def read_schema_authority(self) -> SchemaAuthority: ...

    def run_household_bootstrap(
        self,
        candidate: FreshCandidateArtifacts,
    ) -> str: ...

    def household_bootstrap_is_exact(self) -> bool: ...

    def start_application(self, candidate: FreshCandidateArtifacts) -> None: ...

    def candidate_is_ready(self, candidate: FreshCandidateArtifacts) -> bool: ...

    def run_verified_backup(self, lock: OperationLock) -> str: ...

    def backup_marker_is_verified(self, marker_sha256: str) -> bool: ...

    def consume_bootstrap_input(self) -> None: ...

    def bootstrap_input_exists(self) -> bool: ...

    def persist_candidate_images(self, candidate: FreshCandidateArtifacts) -> None: ...

    def cleanup(self) -> None: ...


@dataclass(frozen=True)
class FreshBootstrapResult:
    revision: str
    status: str


Clock = Callable[[], str]
CrashHook = Callable[[str], None]


def run_fresh_bootstrap(
    command: str,
    token: bytearray,
    *,
    paths: HostPaths,
    adapter: FreshBootstrapAdapter,
    clock: Clock,
    crash_hook: CrashHook | None = None,
) -> FreshBootstrapResult:
    try:
        request = FreshBootstrapRequest.from_command(command)
        _validate_token(token)
        adapter.validate_authority()
        with OperationLock(paths) as lock:
            observation = fresh_bootstrap_state.inspect(paths, lock)
            if observation["status"] == "READY":
                raise FreshBootstrapError("fresh bootstrap is already committed")
            pending = observation["pending"]
            recovering = pending is not None
            adapter.validate_resource_authority(recovering=recovering)

            artifacts = adapter.prepare_artifacts(request, token)
            artifacts.validate_for(request)
            _zeroize(token)

            if pending is None:
                candidate = host_state.stage_release(
                    paths,
                    lock,
                    artifacts.runtime_source,
                    application_revision=request.revision,
                    runtime_config_digest=request.runtime_config_digest,
                    runtime_config_revision=request.revision,
                )
                fresh_bootstrap_state.begin(
                    paths,
                    lock,
                    candidate,
                    actor=request.actor,
                    started_at=clock(),
                )
                newly_started = True
                _crash(crash_hook, "ARTIFACTS_VERIFIED")
            else:
                candidate = _require_matching_pending(
                    pending,
                    request=request,
                    artifacts=artifacts,
                )
                newly_started = False

            return _resume(
                paths=paths,
                lock=lock,
                request=request,
                candidate=candidate,
                artifacts=artifacts,
                adapter=adapter,
                newly_started=newly_started,
                crash_hook=crash_hook,
            )
    except FreshBootstrapInterventionRequired:
        raise
    except Exception as error:
        raise FreshBootstrapError("fresh bootstrap transaction failed") from error
    finally:
        _zeroize(token)
        active_error = sys.exc_info()[0] is not None
        try:
            adapter.cleanup()
        except Exception as cleanup_error:
            if not active_error:
                raise FreshBootstrapError("fresh bootstrap cleanup failed") from cleanup_error


def read_token(source: bytes) -> bytearray:
    from scripts.host_tools.deploy_transaction import read_token as deployment_read_token

    try:
        return deployment_read_token(source)
    except ContractError as error:
        raise FreshBootstrapError("registry token input is invalid") from error


def _resume(
    *,
    paths: HostPaths,
    lock: OperationLock,
    request: FreshBootstrapRequest,
    candidate: ReleaseIdentity,
    artifacts: FreshCandidateArtifacts,
    adapter: FreshBootstrapAdapter,
    newly_started: bool,
    crash_hook: CrashHook | None,
) -> FreshBootstrapResult:
    while True:
        pending = fresh_bootstrap_state.read(paths, lock, required=True)
        assert pending is not None
        phase = pending["phase"]

        if phase == "ARTIFACTS_VERIFIED":
            adapter.start_postgres(artifacts)
            if not adapter.postgres_is_ready(artifacts):
                raise FreshBootstrapError("fresh PostgreSQL readiness failed")
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="POSTGRES_STARTED",
            )
            _crash(crash_hook, "POSTGRES_STARTED")
            continue

        if phase == "POSTGRES_STARTED":
            if not adapter.postgres_is_ready(artifacts):
                raise FreshBootstrapInterventionRequired(
                    "fresh PostgreSQL authority is unavailable"
                )
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="MIGRATION_STARTED",
            )
            _crash(crash_hook, "MIGRATION_STARTED")
            continue

        if phase == "MIGRATION_STARTED":
            adapter.run_migration(artifacts)
            schema = adapter.read_schema_authority()
            _require_schema(schema)
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="MIGRATION_VERIFIED",
                schema_after=schema,
            )
            _crash(crash_hook, "MIGRATION_VERIFIED")
            continue

        schema = pending["schemaAfter"]
        if not isinstance(schema, SchemaAuthority) or adapter.read_schema_authority() != schema:
            raise FreshBootstrapInterventionRequired(
                "fresh bootstrap schema authority changed"
            )

        if phase == "MIGRATION_VERIFIED":
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="BOOTSTRAP_STARTED",
            )
            _crash(crash_hook, "BOOTSTRAP_STARTED")
            continue

        if phase == "BOOTSTRAP_STARTED":
            if not adapter.bootstrap_input_exists():
                raise FreshBootstrapInterventionRequired(
                    "fresh bootstrap input is unavailable"
                )
            status = adapter.run_household_bootstrap(artifacts)
            if status == "verified" and newly_started:
                raise FreshBootstrapInterventionRequired(
                    "fresh bootstrap found preexisting household state"
                )
            if status not in {"created", "verified"}:
                raise FreshBootstrapInterventionRequired(
                    "fresh bootstrap household authority differs"
                )
            if not adapter.household_bootstrap_is_exact():
                raise FreshBootstrapInterventionRequired(
                    "fresh bootstrap household state differs"
                )
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="BOOTSTRAP_VERIFIED",
            )
            _crash(crash_hook, "BOOTSTRAP_VERIFIED")
            continue

        if not adapter.household_bootstrap_is_exact():
            raise FreshBootstrapInterventionRequired(
                "fresh bootstrap household state changed"
            )

        if phase == "BOOTSTRAP_VERIFIED":
            adapter.start_application(artifacts)
            if not adapter.candidate_is_ready(artifacts):
                raise FreshBootstrapError("fresh candidate readiness failed")
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="READINESS_VERIFIED",
            )
            _crash(crash_hook, "READINESS_VERIFIED")
            continue

        if not adapter.candidate_is_ready(artifacts):
            raise FreshBootstrapInterventionRequired(
                "fresh candidate runtime authority changed"
            )

        if phase == "READINESS_VERIFIED":
            marker_sha256 = adapter.run_verified_backup(lock)
            _require_marker(marker_sha256)
            if not adapter.backup_marker_is_verified(marker_sha256):
                raise FreshBootstrapError("fresh bootstrap backup verification failed")
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="BACKUP_VERIFIED",
                backup_marker_sha256=marker_sha256,
            )
            _crash(crash_hook, "BACKUP_VERIFIED")
            continue

        marker = pending["backupMarkerSha256"]
        if not isinstance(marker, str) or not adapter.backup_marker_is_verified(marker):
            raise FreshBootstrapInterventionRequired(
                "fresh bootstrap verified backup authority changed"
            )

        if phase == "BACKUP_VERIFIED":
            adapter.consume_bootstrap_input()
            if adapter.bootstrap_input_exists():
                raise FreshBootstrapError("fresh bootstrap input consumption failed")
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=phase,
                next_phase="INPUT_CONSUMED",
            )
            _crash(crash_hook, "INPUT_CONSUMED")
            continue

        if phase in {"INPUT_CONSUMED", "COMMITTING"}:
            if adapter.bootstrap_input_exists():
                raise FreshBootstrapInterventionRequired(
                    "consumed bootstrap input reappeared"
                )
            adapter.persist_candidate_images(artifacts)
            if phase == "INPUT_CONSUMED":
                fresh_bootstrap_state.advance(
                    paths,
                    lock,
                    expected_phase=phase,
                    next_phase="COMMITTING",
                )
                _crash(crash_hook, "COMMITTING")
            fresh_bootstrap_state.commit(paths, lock)
            return FreshBootstrapResult(request.revision, "SUCCESS")

        raise FreshBootstrapInterventionRequired(
            "fresh bootstrap pending phase is unsupported"
        )


def _require_matching_pending(
    pending: dict[str, object],
    *,
    request: FreshBootstrapRequest,
    artifacts: FreshCandidateArtifacts,
) -> ReleaseIdentity:
    candidate = pending["candidate"]
    if not isinstance(candidate, ReleaseIdentity):
        raise FreshBootstrapInterventionRequired("fresh bootstrap candidate is invalid")
    if (
        candidate.application_revision != request.revision
        or candidate.runtime_config_digest != request.runtime_config_digest
        or candidate.runtime_config_revision != request.revision
        or pending["actor"] != request.actor
        or host_state.release_content_sha256(artifacts.runtime_source)
        != candidate.runtime_config_content_sha256
    ):
        raise FreshBootstrapInterventionRequired(
            "fresh bootstrap recovery request differs"
        )
    return candidate


def _require_schema(schema: SchemaAuthority) -> None:
    if schema.successful_version != EXPECTED_SCHEMA_VERSION:
        raise FreshBootstrapInterventionRequired(
            "fresh bootstrap schema version differs"
        )


def _require_marker(value: str) -> None:
    import re

    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise FreshBootstrapError("fresh bootstrap marker identity is invalid")


def _validate_token(token: bytearray) -> None:
    from scripts.host_tools.deploy_transaction import _validate_token as validate

    validate(token)


def _zeroize(token: bytearray) -> None:
    from scripts.host_tools.deploy_transaction import _zeroize as zeroize

    zeroize(token)


def _crash(hook: CrashHook | None, phase: str) -> None:
    if hook is not None:
        hook(phase)
