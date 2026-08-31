from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from scripts.backup_tools import backup_artifact
from scripts.host_tools import host_state
from scripts.host_tools.deploy_transaction import (
    API_REPOSITORY,
    MAX_TOKEN_BYTES,
    RUNTIME_CONFIG_REPOSITORY,
    WEB_REPOSITORY,
    CandidateArtifacts,
    DeploymentError,
    DeploymentRequest,
    ReporterError,
    RuntimeObservation,
)
from scripts.host_tools.host_state import (
    ContractError,
    HostPaths,
    OperationLock,
    ReleaseIdentity,
    SchemaAuthority,
)
from scripts.release_tools import release_contract
from scripts.status_tools import monitor_worker


DOCKER = Path("/usr/local/bin/docker")
PROJECT_NAME = "our-ledger-production"
APP_ROOT = host_state.PRODUCTION_APP_ROOT
ENV_FILE = APP_ROOT / ".env"
BACKUP_DIRECTORY = Path("/Users/homeserver/Server/backups/our-ledger/data")
HOMEOPS_REPORTER = Path(
    "/Users/homeserver/Server/apps/homeops/runtime-config/current/"
    "scripts/report-homeops-event.py"
)
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 18080
SOURCE_URL = "https://github.com/xxh3898/our-ledger"
MAX_PROCESS_OUTPUT = 1024 * 1024
MAX_ENV_BYTES = 64 * 1024
PROCESS_TIMEOUT_SECONDS = 240
MIGRATION_TIMEOUT_SECONDS = 600
REPORTER_TIMEOUT_SECONDS = 10
TEMPORARY_PARENT = Path("/private/tmp")
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
REPO_DIGEST_PATTERN = re.compile(r"([^@]+)@(sha256:[0-9a-f]{64})")
SCHEMA_QUERY = r"""
exec psql -X \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --tuples-only \
  --no-align \
  --field-separator '|' \
  --set ON_ERROR_STOP=1 \
  --command '
    SELECT installed_rank, version, description, type, script,
           checksum::text, installed_by, success
      FROM flyway_schema_history
     ORDER BY installed_rank
  '
"""


class ProductionDeploymentAdapter:
    def __init__(self, paths: HostPaths):
        if paths != host_state.production_paths():
            raise ContractError("production deployment root authority differs")
        self.paths = paths
        self.runtime_root = Path(__file__).resolve().parents[2]
        self._reporter: monitor_worker.HomeOpsReporter | None = None
        self._docker_config: Path | None = None
        self._temporary_root: Path | None = None
        self._runtime_container: str | None = None
        self._previous: ReleaseIdentity | None = None
        self._candidate: CandidateArtifacts | None = None
        self._candidate_release: Path | None = None
        self._migration_started = False

    def validate_authority(self) -> None:
        if not DOCKER.is_absolute() or not DOCKER.exists() or not os.access(DOCKER, os.X_OK):
            raise DeploymentError("fixed Docker authority is unavailable")
        _require_private_file(ENV_FILE, 0o600)
        _require_private_directory(BACKUP_DIRECTORY, 0o700)
        try:
            backup_artifact.validate_backup_directory_read_only(
                str(self.runtime_root), str(BACKUP_DIRECTORY)
            )
            self._reporter = monitor_worker.validate_homeops_reporter(
                self.runtime_root, str(HOMEOPS_REPORTER)
            )
        except (backup_artifact.ContractError, monitor_worker.ContractError) as error:
            raise DeploymentError("fixed external authority differs") from error
        if _read_env_value(ENV_FILE, "OUR_LEDGER_ORIGIN_PORT") != str(LOOPBACK_PORT):
            raise DeploymentError("fixed loopback origin authority differs")
        _validate_current_image_value(
            _read_env_value(ENV_FILE, "OUR_LEDGER_API_IMAGE"), API_REPOSITORY
        )
        _validate_current_image_value(
            _read_env_value(ENV_FILE, "OUR_LEDGER_WEB_IMAGE"), WEB_REPOSITORY
        )

    def prepare_artifacts(
        self,
        request: DeploymentRequest,
        token: bytearray,
        previous: ReleaseIdentity | None,
    ) -> CandidateArtifacts:
        if previous is None:
            raise DeploymentError("deployment requires a verified current release")
        _require_current_images_match(previous)
        self._previous = previous
        self._temporary_root = _create_private_temporary_root()
        self._docker_config = self._temporary_root / "docker-config"
        self._docker_config.mkdir(mode=0o700)
        _materialize_private_registry_auth(self._docker_config, request.actor, token)

        api_reference = f"{API_REPOSITORY}:{request.revision}"
        web_reference = f"{WEB_REPOSITORY}:{request.revision}"
        for reference, repository in (
            (api_reference, API_REPOSITORY),
            (web_reference, WEB_REPOSITORY),
        ):
            self._run([str(DOCKER), "--config", str(self._docker_config), "pull", reference])
            self._validate_image(reference, repository, request.revision)

        runtime_source = None
        runtime_digest = None
        runtime_revision = None
        if request.mode == "update":
            assert request.runtime_config_digest is not None
            runtime_reference = f"{RUNTIME_CONFIG_REPOSITORY}@{request.runtime_config_digest}"
            self._run(
                [str(DOCKER), "--config", str(self._docker_config), "pull", runtime_reference]
            )
            self._validate_image(
                runtime_reference,
                RUNTIME_CONFIG_REPOSITORY,
                request.revision,
                expected_digest=request.runtime_config_digest,
            )
            runtime_source = self._extract_runtime(runtime_reference)
            runtime_digest = request.runtime_config_digest
            runtime_revision = request.revision
            self._candidate_release = self.paths.releases / request.runtime_config_digest.removeprefix(
                "sha256:"
            )
        else:
            self._candidate_release = self.paths.releases / previous.release_name

        candidate = CandidateArtifacts(
            revision=request.revision,
            api_reference=api_reference,
            web_reference=web_reference,
            runtime_config_digest=runtime_digest,
            runtime_config_revision=runtime_revision,
            runtime_source=runtime_source,
        )
        self._candidate = candidate
        self._validate_candidate_compose(candidate, runtime_source)
        return candidate

    def quiesce_writer(self, previous: ReleaseIdentity | None) -> None:
        if previous is None:
            return
        self._run(
            self._compose(previous, ["stop", "--timeout", "60", "api"]),
            environment=_revision_environment(previous.application_revision),
        )

    def run_verified_backup(self, lock: OperationLock) -> None:
        from scripts.host_tools.production_host import run_backup_core

        identity = self._previous
        if identity is None:
            raise DeploymentError("predeploy backup requires a current release")
        core_path = (
            self.paths.releases
            / identity.release_name
            / "scripts"
            / "backup_tools"
            / "backup_core.sh"
        )
        result = run_backup_core(
            [
                "--project-name",
                PROJECT_NAME,
                "--env-file",
                str(ENV_FILE),
                "--backup-dir",
                str(BACKUP_DIRECTORY),
            ],
            paths=self.paths,
            lock=lock,
            core_path=core_path,
            runner=lambda arguments: self._run(arguments).returncode,
        )
        if result != 0:
            raise DeploymentError("verified predeploy backup failed")

    def read_schema_authority(self) -> SchemaAuthority:
        identity = self._candidate_identity() if self._migration_started else self._previous
        if identity is None:
            raise DeploymentError("schema authority requires a runtime release")
        result = self._run(
            self._compose(
                identity,
                ["exec", "-T", "postgres", "sh", "-ceu", SCHEMA_QUERY],
            ),
            environment=(
                _candidate_environment(self._candidate)
                if self._migration_started and self._candidate is not None
                else _revision_environment(identity.application_revision)
            ),
        )
        rows = [line for line in result.stdout.decode("utf-8").splitlines() if line]
        if not rows:
            raise DeploymentError("Flyway history is unavailable")
        parsed = [row.split("|") for row in rows]
        if any(len(row) != 8 for row in parsed):
            raise DeploymentError("Flyway history shape is invalid")
        failed = sum(1 for row in parsed if row[7] != "t")
        successful_versions = [row[1] for row in parsed if row[7] == "t" and row[1]]
        if failed != 0 or not successful_versions:
            raise DeploymentError("Flyway history authority is invalid")
        history = "\n".join(rows).encode("utf-8")
        return SchemaAuthority(
            successful_versions[-1],
            failed,
            hashlib.sha256(history).hexdigest(),
        )

    def run_candidate_migration(self, candidate: CandidateArtifacts) -> None:
        self._migration_started = True
        result = self._run(
            self._compose(
                self._candidate_identity(),
                ["--profile", "migration", "run", "--rm", "--no-deps", "api-migration"],
            ),
            environment=_candidate_environment(candidate),
            timeout=MIGRATION_TIMEOUT_SECONDS,
        )
        lines = result.stdout.decode("utf-8", errors="replace").splitlines()
        if lines.count("migration-validation: success") != 1:
            raise DeploymentError("candidate migration validation marker differs")

    def cutover_candidate(self, candidate: CandidateArtifacts) -> None:
        self._run(
            self._compose(
                self._candidate_identity(),
                [
                    "up",
                    "--detach",
                    "--no-build",
                    "--pull",
                    "never",
                    "--no-deps",
                    "--wait",
                    "--wait-timeout",
                    "180",
                    "api",
                    "web",
                ],
            ),
            environment=_candidate_environment(candidate),
        )

    def candidate_is_ready(self, candidate: CandidateArtifacts) -> bool:
        if not self._services_ready(
            candidate.revision,
            self._candidate_identity(),
            candidate,
        ):
            return False
        return _loopback_status("/healthz") == 200 and _loopback_status("/api/v1/me") == 401

    def persist_candidate_images(self, candidate: CandidateArtifacts) -> None:
        _replace_env_images(ENV_FILE, candidate.api_reference, candidate.web_reference)

    def recover_previous(self, previous: ReleaseIdentity | None) -> bool:
        if previous is None:
            try:
                identity = self._candidate_identity()
                self._run(
                    self._compose(identity, ["stop", "--timeout", "60", "api", "web"]),
                    environment=(
                        _candidate_environment(self._candidate)
                        if self._candidate is not None
                        else None
                    ),
                )
                return True
            except (DeploymentError, OSError):
                return False
        api = f"{API_REPOSITORY}:{previous.application_revision}"
        web = f"{WEB_REPOSITORY}:{previous.application_revision}"
        synthetic = CandidateArtifacts(
            revision=previous.application_revision,
            api_reference=api,
            web_reference=web,
            runtime_config_digest=None,
            runtime_config_revision=None,
            runtime_source=None,
        )
        try:
            self._run(
                self._compose(
                    previous,
                    [
                        "up",
                        "--detach",
                        "--no-build",
                        "--pull",
                        "never",
                        "--no-deps",
                        "--wait",
                        "--wait-timeout",
                        "180",
                        "api",
                        "web",
                    ],
                ),
                environment=_candidate_environment(synthetic),
            )
            if not self._services_ready(
                previous.application_revision,
                previous,
                synthetic,
            ):
                return False
            _replace_env_images(ENV_FILE, api, web)
            return True
        except (DeploymentError, OSError):
            return False

    def observe_runtime(
        self,
        candidate: ReleaseIdentity,
        previous: ReleaseIdentity | None,
    ) -> RuntimeObservation:
        self._previous = previous
        self._candidate_release = self.paths.releases / candidate.release_name
        self._candidate = CandidateArtifacts(
            revision=candidate.application_revision,
            api_reference=f"{API_REPOSITORY}:{candidate.application_revision}",
            web_reference=f"{WEB_REPOSITORY}:{candidate.application_revision}",
            runtime_config_digest=candidate.runtime_config_digest,
            runtime_config_revision=candidate.runtime_config_revision,
            runtime_source=None,
        )
        self._migration_started = True
        candidate_artifacts = self._candidate
        candidate_ready = self._services_ready(
            candidate.application_revision,
            candidate,
            candidate_artifacts,
        )
        previous_artifacts = (
            CandidateArtifacts(
                revision=previous.application_revision,
                api_reference=f"{API_REPOSITORY}:{previous.application_revision}",
                web_reference=f"{WEB_REPOSITORY}:{previous.application_revision}",
                runtime_config_digest=None,
                runtime_config_revision=None,
                runtime_source=None,
            )
            if previous is not None
            else None
        )
        previous_ready = (
            previous is not None
            and self._services_ready(
                previous.application_revision,
                previous,
                previous_artifacts,
            )
        )
        running = None
        if candidate_ready:
            running = candidate.application_revision
        elif previous_ready and previous is not None:
            running = previous.application_revision
        return RuntimeObservation(
            schema=self.read_schema_authority(),
            candidate_ready=candidate_ready,
            previous_ready=previous_ready,
            running_revision=running,
        )

    def report_deployment(self, payload: dict[str, object]) -> None:
        if self._reporter is None:
            raise ReporterError("HomeOps reporter authority is unavailable")
        try:
            monitor_worker._revalidate_homeops_reporter(self._reporter)
        except monitor_worker.ContractError as error:
            raise ReporterError("HomeOps reporter did not accept deployment") from error
        body = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(body) > 16 * 1024:
            raise ReporterError("HomeOps deployment payload is too large")
        try:
            result = subprocess.run(
                [str(self._reporter.path), "deployments"],
                input=body,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
                timeout=REPORTER_TIMEOUT_SECONDS,
                env=_safe_process_environment(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReporterError("HomeOps reporter did not accept deployment") from error
        if result.returncode != 0:
            raise ReporterError("HomeOps reporter did not accept deployment")

    def cleanup(self) -> None:
        failed = False
        if self._runtime_container is not None:
            try:
                result = subprocess.run(
                    [str(DOCKER), "rm", "--force", self._runtime_container],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    shell=False,
                    timeout=PROCESS_TIMEOUT_SECONDS,
                    env=_safe_process_environment(),
                )
                failed = failed or result.returncode != 0
            except (OSError, subprocess.SubprocessError):
                failed = True
            self._runtime_container = None
        if self._temporary_root is not None and self._temporary_root.exists():
            try:
                shutil.rmtree(self._temporary_root)
            except OSError:
                failed = True
        self._docker_config = None
        self._temporary_root = None
        if failed:
            raise DeploymentError("deployment temporary authority cleanup failed")

    def _run(
        self,
        arguments: Sequence[str],
        *,
        input_bytes: bytes | None = None,
        environment: Mapping[str, str] | None = None,
        timeout: int = PROCESS_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            result = subprocess.run(
                list(arguments),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
                env=(
                    dict(environment)
                    if environment is not None
                    else _safe_process_environment()
                ),
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DeploymentError("fixed production command failed") from error
        if len(result.stdout) > MAX_PROCESS_OUTPUT or len(result.stderr) > MAX_PROCESS_OUTPUT:
            raise DeploymentError("fixed production command output exceeded its bound")
        if result.returncode != 0:
            raise DeploymentError("fixed production command failed")
        return result

    def _validate_image(
        self,
        reference: str,
        repository: str,
        revision: str,
        *,
        expected_digest: str | None = None,
    ) -> None:
        result = self._run([str(DOCKER), "image", "inspect", reference])
        try:
            values = json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DeploymentError("candidate image metadata is invalid") from error
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise DeploymentError("candidate image metadata is invalid")
        value = values[0]
        labels = value.get("Config", {}).get("Labels", {})
        repo_digests = value.get("RepoDigests", [])
        valid_repo_digests = (
            {
                item
                for item in repo_digests
                if isinstance(item, str)
                and (match := REPO_DIGEST_PATTERN.fullmatch(item)) is not None
                and match.group(1) == repository
            }
            if isinstance(repo_digests, list)
            else set()
        )
        if (
            not isinstance(value.get("Id"), str)
            or IMAGE_ID_PATTERN.fullmatch(value["Id"]) is None
            or value.get("Os") != "linux"
            or value.get("Architecture") != "arm64"
            or not isinstance(labels, dict)
            or labels.get("org.opencontainers.image.source") != SOURCE_URL
            or labels.get("org.opencontainers.image.revision") != revision
            or labels.get("org.opencontainers.image.version") != revision
            or not isinstance(repo_digests, list)
            or not valid_repo_digests
        ):
            raise DeploymentError("candidate image identity differs")
        if (
            expected_digest is not None
            and f"{repository}@{expected_digest}" not in valid_repo_digests
        ):
            raise DeploymentError("runtime config digest differs")

    def _extract_runtime(self, reference: str) -> Path:
        if self._temporary_root is None:
            raise DeploymentError("runtime extraction root is unavailable")
        archive = self._temporary_root / "runtime.tar"
        extracted = self._temporary_root / "runtime"
        self._runtime_container = f"our-ledger-runtime-{uuid.uuid4().hex}"
        self._run(
            [
                str(DOCKER),
                "create",
                "--platform",
                "linux/arm64",
                "--name",
                self._runtime_container,
                reference,
            ]
        )
        self._run(
            [
                str(DOCKER),
                "export",
                "--output",
                str(archive),
                self._runtime_container,
            ]
        )
        _extract_verified_runtime(archive, extracted)
        return extracted

    def _validate_candidate_compose(
        self,
        candidate: CandidateArtifacts,
        runtime_source: Path | None,
    ) -> None:
        if runtime_source is not None:
            compose_file = runtime_source / "compose.yaml"
            project_directory = runtime_source
        else:
            identity = self._previous
            if identity is None:
                raise DeploymentError("keep candidate has no current runtime config")
            project_directory = self.paths.releases / identity.release_name
            compose_file = project_directory / "compose.yaml"
        environment = _candidate_environment(candidate)
        self._run(
            [
                str(DOCKER),
                "compose",
                "--project-name",
                PROJECT_NAME,
                "--project-directory",
                str(project_directory),
                "--env-file",
                str(ENV_FILE),
                "--file",
                str(compose_file),
                "config",
                "--quiet",
            ],
            environment=environment,
        )

    def _candidate_identity(self) -> ReleaseIdentity:
        if self._candidate_release is None or self._candidate is None:
            raise DeploymentError("candidate runtime identity is unavailable")
        if self._candidate.runtime_config_digest is None:
            if self._previous is None:
                raise DeploymentError("candidate current runtime identity is unavailable")
            digest = self._previous.runtime_config_digest
            revision = self._previous.runtime_config_revision
            content = self._previous.runtime_config_content_sha256
        else:
            digest = self._candidate.runtime_config_digest
            revision = self._candidate.runtime_config_revision
            content = host_state.release_content_sha256(self._candidate_release)
        assert revision is not None
        return ReleaseIdentity(self._candidate.revision, digest, revision, content)

    def _compose(
        self,
        identity: ReleaseIdentity,
        tail: Sequence[str],
    ) -> list[str]:
        release = self.paths.releases / identity.release_name
        arguments = [
            str(DOCKER),
            "compose",
            "--project-name",
            PROJECT_NAME,
            "--project-directory",
            str(release),
            "--env-file",
            str(ENV_FILE),
            "--file",
            str(release / "compose.yaml"),
        ]
        arguments.extend(tail)
        return arguments

    def _services_ready(
        self,
        revision: str,
        identity: ReleaseIdentity,
        candidate: CandidateArtifacts | None = None,
    ) -> bool:
        try:
            for service in ("postgres", "api", "web"):
                container = self._run(
                    self._compose(identity, ["ps", "--all", "--quiet", service]),
                    environment=(
                        _candidate_environment(candidate)
                        if candidate is not None
                        else None
                    ),
                ).stdout.decode("utf-8").strip()
                if not container or "\n" in container:
                    return False
                inspected = json.loads(
                    self._run([str(DOCKER), "inspect", container]).stdout
                )
                if not isinstance(inspected, list) or len(inspected) != 1:
                    return False
                value = inspected[0]
                health = value.get("State", {}).get("Health", {}).get("Status")
                if health != "healthy":
                    return False
                if service in {"api", "web"}:
                    if candidate is None:
                        return False
                    labels = value.get("Config", {}).get("Labels", {})
                    expected_image = (
                        candidate.api_reference if service == "api" else candidate.web_reference
                    )
                    if (
                        value.get("Config", {}).get("Image") != expected_image
                        or labels.get("org.opencontainers.image.revision") != revision
                    ):
                        return False
            return True
        except (DeploymentError, UnicodeDecodeError, json.JSONDecodeError):
            return False


def _candidate_environment(candidate: CandidateArtifacts) -> dict[str, str]:
    environment = _safe_process_environment()
    environment["OUR_LEDGER_API_IMAGE"] = candidate.api_reference
    environment["OUR_LEDGER_WEB_IMAGE"] = candidate.web_reference
    return environment


def _revision_environment(revision: str) -> dict[str, str]:
    return _candidate_environment(
        CandidateArtifacts(
            revision=revision,
            api_reference=f"{API_REPOSITORY}:{revision}",
            web_reference=f"{WEB_REPOSITORY}:{revision}",
            runtime_config_digest=None,
            runtime_config_revision=None,
            runtime_source=None,
        )
    )


def _safe_process_environment() -> dict[str, str]:
    return {"LANG": "C", "LC_ALL": "C", "PATH": SAFE_PATH}


def _create_private_temporary_root(parent: Path = TEMPORARY_PARENT) -> Path:
    try:
        parent_stat = os.lstat(parent)
        parent_canonical = parent.resolve(strict=True)
    except OSError as error:
        raise DeploymentError("fixed deployment temporary parent is unavailable") from error
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or parent_canonical != parent
        or not (parent_stat.st_mode & stat.S_ISVTX)
        or stat.S_IMODE(parent_stat.st_mode) & 0o002 == 0
    ):
        raise DeploymentError("fixed deployment temporary parent authority differs")
    try:
        created = Path(tempfile.mkdtemp(prefix="our-ledger-deploy-", dir=parent))
        created.chmod(0o700)
        _require_private_directory(created, 0o700)
    except OSError as error:
        raise DeploymentError("private deployment temporary root could not be created") from error
    if created.is_relative_to(APP_ROOT) or APP_ROOT.is_relative_to(created):
        shutil.rmtree(created)
        raise DeploymentError("deployment temporary root overlaps fixed app root")
    return created


def _materialize_private_registry_auth(
    config_directory: Path,
    actor: str,
    token: bytearray,
) -> Path:
    try:
        release_contract.validate_actor(actor)
    except release_contract.ContractError as error:
        raise DeploymentError("private registry auth input is invalid") from error
    if (
        not isinstance(token, bytearray)
        or not token
        or len(token) > MAX_TOKEN_BYTES
        or any(value in token for value in (0, 10, 13))
    ):
        raise DeploymentError("private registry auth input is invalid")
    if not config_directory.is_absolute() or config_directory.name != "docker-config":
        raise DeploymentError("private registry auth directory differs")
    try:
        parent = config_directory.parent
        _require_private_directory(parent, 0o700)
        _require_private_directory(config_directory, 0o700)
        if (
            parent.resolve(strict=True) != parent
            or config_directory.resolve(strict=True) != config_directory
        ):
            raise DeploymentError("private registry auth directory differs")
    except OSError as error:
        raise DeploymentError("private registry auth directory differs") from error

    config_path = config_directory / "config.json"
    credential = bytearray(actor.encode("ascii"))
    credential.extend(b":")
    credential.extend(token)
    encoded_auth = bytearray(base64.b64encode(credential))
    payload = bytearray(b'{"auths":{"ghcr.io":{"auth":"')
    payload.extend(encoded_auth)
    payload.extend(b'"}}}')
    descriptor: int | None = None
    opened: os.stat_result | None = None
    payload_view: memoryview | None = None
    try:
        descriptor = os.open(
            config_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        offset = 0
        payload_view = memoryview(payload)
        while offset < len(payload):
            write_view = payload_view[offset:]
            try:
                written = os.write(descriptor, write_view)
            finally:
                write_view.release()
            if written <= 0:
                raise OSError("private registry auth write made no progress")
            offset += written
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        os.close(descriptor)
        descriptor = None
        actual = _require_private_file(config_path, 0o600)
        if (
            opened is None
            or (opened.st_dev, opened.st_ino) != (actual.st_dev, actual.st_ino)
            or actual.st_size != len(payload)
            or config_path.parent != config_directory
        ):
            raise DeploymentError("private registry auth file differs")
        host_state._fsync_directory(config_directory)
        return config_path
    except (OSError, DeploymentError) as error:
        raise DeploymentError("private registry auth materialization failed") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if payload_view is not None:
                payload_view.release()
        finally:
            for sensitive in (credential, encoded_auth, payload):
                for index in range(len(sensitive)):
                    sensitive[index] = 0
                sensitive.clear()


def _require_private_file(path: Path, mode: int) -> os.stat_result:
    details = os.lstat(path)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.geteuid()
        or stat.S_IMODE(details.st_mode) != mode
        or details.st_nlink != 1
        or path.resolve(strict=True) != path
    ):
        raise DeploymentError("fixed private file authority differs")
    return details


def _require_private_directory(path: Path, mode: int) -> None:
    details = os.lstat(path)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.geteuid()
        or stat.S_IMODE(details.st_mode) != mode
        or path.resolve(strict=True) != path
    ):
        raise DeploymentError("fixed private directory authority differs")


def _read_env_value(path: Path, key: str) -> str:
    matches = []
    try:
        content = _read_private_bytes(path, 0o600, MAX_ENV_BYTES).decode("utf-8")
    except UnicodeDecodeError as error:
        raise DeploymentError("fixed env authority differs") from error
    for line in content.splitlines():
        if line.startswith(f"{key}="):
            matches.append(line.split("=", 1)[1])
    if len(matches) != 1 or not matches[0]:
        raise DeploymentError("fixed env authority differs")
    return matches[0]


def _validate_current_image_value(value: str, repository: str) -> None:
    prefix = f"{repository}:"
    revision = value.removeprefix(prefix)
    if value != f"{prefix}{revision}" or not host_state.REVISION_PATTERN.fullmatch(revision):
        raise DeploymentError("current image authority differs")


def _require_current_images_match(identity: ReleaseIdentity) -> None:
    expected = identity.application_revision
    if (
        _read_env_value(ENV_FILE, "OUR_LEDGER_API_IMAGE")
        != f"{API_REPOSITORY}:{expected}"
        or _read_env_value(ENV_FILE, "OUR_LEDGER_WEB_IMAGE")
        != f"{WEB_REPOSITORY}:{expected}"
    ):
        raise DeploymentError("current image env and committed state differ")


def _read_private_bytes(path: Path, mode: int, maximum: int) -> bytes:
    before = _require_private_file(path, mode)
    if before.st_size > maximum:
        raise DeploymentError("fixed private file exceeds its size bound")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DeploymentError("fixed private file could not be opened") from error
    try:
        after = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after.st_mode)
            or after.st_uid != os.geteuid()
            or stat.S_IMODE(after.st_mode) != mode
            or after.st_nlink != 1
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise DeploymentError("fixed private file identity changed")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum:
            raise DeploymentError("fixed private file exceeds its size bound")
        return content
    finally:
        os.close(descriptor)


def _replace_env_images(path: Path, api_reference: str, web_reference: str) -> None:
    original = _require_private_file(path, 0o600)
    source = _read_private_bytes(path, 0o600, MAX_ENV_BYTES)
    if b"\0" in source:
        raise DeploymentError("fixed env payload is invalid")
    lines = source.decode("utf-8").splitlines(keepends=True)
    counts = {"OUR_LEDGER_API_IMAGE": 0, "OUR_LEDGER_WEB_IMAGE": 0}
    replacements = {
        "OUR_LEDGER_API_IMAGE": api_reference,
        "OUR_LEDGER_WEB_IMAGE": web_reference,
    }
    result = []
    for line in lines:
        replaced = False
        for key, value in replacements.items():
            if line.startswith(f"{key}="):
                ending = "\n" if line.endswith("\n") else ""
                result.append(f"{key}={value}{ending}")
                counts[key] += 1
                replaced = True
                break
        if not replaced:
            result.append(line)
    if set(counts.values()) != {1}:
        raise DeploymentError("fixed image env keys differ")
    payload = "".join(result).encode("utf-8")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        current = _require_private_file(path, 0o600)
        if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
            raise DeploymentError("fixed env authority changed during update")
        os.replace(temporary, path)
        host_state._fsync_directory(path.parent)
    except OSError as error:
        raise DeploymentError("fixed image env update failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _extract_verified_runtime(archive: Path, destination: Path) -> None:
    members: dict[str, tarfile.TarInfo] = {}
    directories: set[str] = set()
    runtime_root_seen = False
    with tarfile.open(archive, "r") as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            normalized_name = member.name[:-1] if member.name.endswith("/") else member.name
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or normalized_name != path.as_posix()
            ):
                raise DeploymentError("runtime config archive path is unsafe")
            if path.parts[0] != "runtime":
                continue
            if len(path.parts) == 1:
                if runtime_root_seen or not member.isdir():
                    raise DeploymentError("runtime config archive root is invalid")
                runtime_root_seen = True
                continue
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in members or relative in directories:
                raise DeploymentError("runtime config archive contains duplicates")
            if member.isdir():
                directories.add(relative)
            elif member.isfile():
                if member.size > host_state.MAX_RELEASE_FILE_SIZE:
                    raise DeploymentError("runtime config archive file is too large")
                members[relative] = member
            else:
                raise DeploymentError("runtime config archive contains non-regular material")
        if not runtime_root_seen:
            raise DeploymentError("runtime config archive root is missing")

        manifest_member = members.get(host_state.RUNTIME_MANIFEST)
        if manifest_member is None:
            profile = host_state.legacy_release_profile()
        else:
            if (
                stat.S_IMODE(manifest_member.mode) != 0o600
                or manifest_member.size <= 0
                or manifest_member.size > host_state.MAX_RUNTIME_MANIFEST_SIZE
            ):
                raise DeploymentError("runtime config manifest metadata differs")
            manifest_source = bundle.extractfile(manifest_member)
            if manifest_source is None:
                raise DeploymentError("runtime config manifest is unavailable")
            with manifest_source:
                manifest_payload = manifest_source.read(
                    host_state.MAX_RUNTIME_MANIFEST_SIZE + 1
                )
            if len(manifest_payload) != manifest_member.size:
                raise DeploymentError("runtime config manifest content differs")
            try:
                profile = host_state.parse_runtime_manifest(manifest_payload)
            except host_state.ContractError as error:
                raise DeploymentError("runtime config manifest is invalid") from error

        expected_files = profile.all_file_modes
        if directories != profile.directories or set(members) != set(expected_files):
            raise DeploymentError("runtime config archive allowlist differs")
        for relative, expected_mode in expected_files.items():
            if stat.S_IMODE(members[relative].mode) != expected_mode:
                raise DeploymentError("runtime config archive mode differs")

        try:
            destination.mkdir(mode=0o700)
            destination.chmod(0o700)
        except OSError as error:
            raise DeploymentError("runtime config extraction root is unavailable") from error
        for relative in sorted(directories, key=lambda item: item.count("/")):
            target_directory = destination / relative
            target_directory.mkdir(mode=0o700)
            target_directory.chmod(0o700)
        for relative, expected_mode in expected_files.items():
            member = members[relative]
            source = bundle.extractfile(member)
            if source is None:
                raise DeploymentError("runtime config archive content is unavailable")
            target = destination / relative
            with source, target.open("xb") as output:
                copied = 0
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                    copied += len(chunk)
            if copied != member.size:
                raise DeploymentError("runtime config archive content differs")
            target.chmod(expected_mode)
    host_state.release_content_sha256(destination)


def _loopback_status(path: str) -> int:
    connection = http.client.HTTPConnection(LOOPBACK_HOST, LOOPBACK_PORT, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read(64 * 1024)
        return response.status
    except (OSError, http.client.HTTPException):
        return 0
    finally:
        connection.close()
