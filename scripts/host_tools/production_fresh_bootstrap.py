from __future__ import annotations

import hashlib
import datetime as dt
import json
import os
import stat
from pathlib import Path
import sys

from scripts.backup_tools import backup_artifact
from scripts.host_tools import host_state
from scripts.host_tools.deploy_transaction import (
    API_REPOSITORY,
    RUNTIME_CONFIG_REPOSITORY,
    WEB_REPOSITORY,
    CandidateArtifacts,
    DeploymentError,
)
from scripts.host_tools.fresh_host_bootstrap import (
    FreshBootstrapError,
    FreshBootstrapRequest,
    FreshCandidateArtifacts,
)
from scripts.host_tools.host_state import HostPaths, OperationLock, SchemaAuthority
from scripts.host_tools.production_deploy import (
    APP_ROOT,
    BACKUP_DIRECTORY,
    DOCKER,
    ENV_FILE,
    PROJECT_NAME,
    ProductionDeploymentAdapter,
    _candidate_environment,
    _read_env_value,
    _read_private_bytes,
    _replace_env_images,
    _require_private_directory,
    _require_private_file,
    _validate_current_image_value,
)


BOOTSTRAP_INGRESS_ROOT = APP_ROOT / "bootstrap-ingress"
BOOTSTRAP_INPUT = APP_ROOT / "household-bootstrap.json"
MAX_BOOTSTRAP_INPUT_BYTES = 8 * 1024
ALLOWED_SERVICES = {"postgres", "api", "web"}
EXPECTED_NETWORKS = {
    f"{PROJECT_NAME}_application",
    f"{PROJECT_NAME}_database",
}
EXPECTED_VOLUMES = {f"{PROJECT_NAME}_postgres-data"}
HOUSEHOLD_STATE_QUERY = r"""
exec psql -X \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --tuples-only \
  --no-align \
  --set ON_ERROR_STOP=1 \
  --command '
    SELECT
      (SELECT COUNT(*) FROM users) || '"'"':'"'"' ||
      (SELECT COUNT(*) FROM households) || '"'"':'"'"' ||
      (SELECT COUNT(*) FROM household_members) || '"'"':'"'"' ||
      (SELECT string_agg(role, '"'"','"'"' ORDER BY role) FROM household_members) || '"'"':'"'"' ||
      (SELECT base_currency || '"'"':'"'"' || timezone FROM households)
  '
"""


class ProductionFreshBootstrapAdapter(ProductionDeploymentAdapter):
    def __init__(self, paths: HostPaths):
        super().__init__(paths)

    def validate_authority(self) -> None:
        if not DOCKER.is_absolute() or not DOCKER.exists() or not os.access(DOCKER, os.X_OK):
            raise FreshBootstrapError("fixed Docker authority is unavailable")
        _require_private_file(ENV_FILE, 0o600)
        _require_private_directory(BACKUP_DIRECTORY, 0o700)
        try:
            backup_artifact.validate_backup_directory_read_only(
                str(BOOTSTRAP_INGRESS_ROOT), str(BACKUP_DIRECTORY)
            )
            _validate_ingress_source()
        except (backup_artifact.ContractError, OSError, DeploymentError) as error:
            raise FreshBootstrapError("fixed fresh bootstrap authority differs") from error
        if _read_env_value(ENV_FILE, "OUR_LEDGER_ORIGIN_PORT") != "18080":
            raise FreshBootstrapError("fixed loopback authority differs")
        _validate_current_image_value(
            _read_env_value(ENV_FILE, "OUR_LEDGER_API_IMAGE"), API_REPOSITORY
        )
        _validate_current_image_value(
            _read_env_value(ENV_FILE, "OUR_LEDGER_WEB_IMAGE"), WEB_REPOSITORY
        )
        _require_disjoint_authorities()

    def validate_resource_authority(self, *, recovering: bool) -> None:
        if os.path.lexists(BOOTSTRAP_INPUT):
            _require_private_file(BOOTSTRAP_INPUT, 0o600)
            _read_private_bytes(BOOTSTRAP_INPUT, 0o600, MAX_BOOTSTRAP_INPUT_BYTES)
        elif not recovering:
            raise FreshBootstrapError("fixed bootstrap input is unavailable")

        resources = self._project_resources()
        if not recovering and any(resources.values()):
            raise FreshBootstrapError("fresh production resources already exist")
        if recovering:
            self._validate_recovery_resources(resources)

        inventory = backup_artifact.inventory(BACKUP_DIRECTORY)
        if not recovering and (
            inventory["valid"]
            or inventory["invalid"]
            or inventory["incomplete"]
            or inventory["foreign"]
            or inventory["lastSuccessValid"]
        ):
            raise FreshBootstrapError("fresh backup authority is not empty")

    def prepare_artifacts(
        self,
        request: FreshBootstrapRequest,
        token: bytearray,
    ) -> FreshCandidateArtifacts:
        from scripts.host_tools.production_deploy import _create_private_temporary_root

        self._temporary_root = _create_private_temporary_root()
        self._docker_config = self._temporary_root / "docker-config"
        self._docker_config.mkdir(mode=0o700)
        self._run(
            [
                str(DOCKER),
                "--config",
                str(self._docker_config),
                "login",
                "ghcr.io",
                "--username",
                request.actor,
                "--password-stdin",
            ],
            input_bytes=bytes(token),
        )

        api_reference = f"{API_REPOSITORY}:{request.revision}"
        web_reference = f"{WEB_REPOSITORY}:{request.revision}"
        for reference, repository in (
            (api_reference, API_REPOSITORY),
            (web_reference, WEB_REPOSITORY),
        ):
            self._run([str(DOCKER), "--config", str(self._docker_config), "pull", reference])
            self._validate_image(reference, repository, request.revision)

        runtime_reference = (
            f"{RUNTIME_CONFIG_REPOSITORY}@{request.runtime_config_digest}"
        )
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
        if host_state.release_content_sha256(
            BOOTSTRAP_INGRESS_ROOT
        ) != host_state.release_content_sha256(runtime_source):
            raise FreshBootstrapError("bootstrap ingress and candidate runtime differ")

        base_candidate = CandidateArtifacts(
            revision=request.revision,
            api_reference=api_reference,
            web_reference=web_reference,
            runtime_config_digest=request.runtime_config_digest,
            runtime_config_revision=request.revision,
            runtime_source=runtime_source,
        )
        self._candidate = base_candidate
        self._candidate_release = self.paths.releases / request.runtime_config_digest.removeprefix(
            "sha256:"
        )
        self._validate_candidate_compose(base_candidate, runtime_source)
        return FreshCandidateArtifacts(
            revision=request.revision,
            api_reference=api_reference,
            web_reference=web_reference,
            runtime_config_digest=request.runtime_config_digest,
            runtime_config_revision=request.revision,
            runtime_source=runtime_source,
        )

    def start_postgres(self, candidate: FreshCandidateArtifacts) -> None:
        base = self._base_candidate(candidate)
        self._run(
            self._compose(
                self._candidate_identity(),
                [
                    "up",
                    "--detach",
                    "--no-build",
                    "--pull",
                    "never",
                    "--wait",
                    "--wait-timeout",
                    "120",
                    "postgres",
                ],
            ),
            environment=_candidate_environment(base),
        )

    def postgres_is_ready(self, candidate: FreshCandidateArtifacts) -> bool:
        try:
            base = self._base_candidate(candidate)
            container = self._run(
                self._compose(
                    self._candidate_identity(),
                    ["ps", "--all", "--quiet", "postgres"],
                ),
                environment=_candidate_environment(base),
            ).stdout.decode("utf-8").strip()
            if not container or "\n" in container:
                return False
            value = json.loads(self._run([str(DOCKER), "inspect", container]).stdout)
            return (
                isinstance(value, list)
                and len(value) == 1
                and value[0].get("State", {}).get("Health", {}).get("Status") == "healthy"
                and value[0].get("Config", {}).get("Labels", {}).get(
                    "com.docker.compose.project"
                )
                == PROJECT_NAME
                and value[0].get("Config", {}).get("Labels", {}).get(
                    "com.docker.compose.service"
                )
                == "postgres"
            )
        except (DeploymentError, UnicodeDecodeError, json.JSONDecodeError):
            return False

    def run_migration(self, candidate: FreshCandidateArtifacts) -> None:
        super().run_candidate_migration(self._base_candidate(candidate))

    def read_schema_authority(self) -> SchemaAuthority:
        self._migration_started = True
        return super().read_schema_authority()

    def run_household_bootstrap(self, candidate: FreshCandidateArtifacts) -> str:
        payload = bytearray(
            _read_private_bytes(BOOTSTRAP_INPUT, 0o600, MAX_BOOTSTRAP_INPUT_BYTES)
        )
        try:
            result = self._run(
                self._compose(
                    self._candidate_identity(),
                    [
                        "--profile",
                        "bootstrap",
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        "api-bootstrap",
                    ],
                ),
                input_bytes=bytes(payload),
                environment=_candidate_environment(self._base_candidate(candidate)),
                timeout=600,
            )
        finally:
            for index in range(len(payload)):
                payload[index] = 0
            payload.clear()
        lines = result.stdout.decode("utf-8", errors="replace").splitlines()
        markers = [
            marker
            for marker in ("created", "verified")
            if lines.count(f"household-bootstrap: {marker}") == 1
        ]
        if len(markers) != 1:
            raise FreshBootstrapError("household bootstrap marker differs")
        return markers[0]

    def household_bootstrap_is_exact(self) -> bool:
        try:
            result = self._run(
                self._compose(
                    self._candidate_identity(),
                    ["exec", "-T", "postgres", "sh", "-ceu", HOUSEHOLD_STATE_QUERY],
                ),
                environment=_candidate_environment(self._candidate),
            )
            return result.stdout.decode("utf-8").strip() == (
                "2:1:2:MEMBER,OWNER:KRW:Asia/Seoul"
            )
        except (DeploymentError, UnicodeDecodeError):
            return False

    def start_application(self, candidate: FreshCandidateArtifacts) -> None:
        super().cutover_candidate(self._base_candidate(candidate))

    def candidate_is_ready(self, candidate: FreshCandidateArtifacts) -> bool:
        return super().candidate_is_ready(self._base_candidate(candidate))

    def run_verified_backup(self, lock: OperationLock) -> str:
        from scripts.host_tools.production_host import run_backup_core

        core_path = (
            self.paths.releases
            / self._candidate_identity().release_name
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
            raise FreshBootstrapError("first verified backup failed")
        marker = BACKUP_DIRECTORY / "last-success.json"
        _require_private_file(marker, 0o600)
        return hashlib.sha256(_read_private_bytes(marker, 0o600, 16 * 1024)).hexdigest()

    def backup_marker_is_verified(self, marker_sha256: str) -> bool:
        try:
            marker = BACKUP_DIRECTORY / "last-success.json"
            actual = hashlib.sha256(
                _read_private_bytes(marker, 0o600, 16 * 1024)
            ).hexdigest()
            return actual == marker_sha256 and backup_artifact.inventory(
                BACKUP_DIRECTORY
            )["lastSuccessValid"]
        except (OSError, DeploymentError, backup_artifact.ContractError):
            return False

    def consume_bootstrap_input(self) -> None:
        if not os.path.lexists(BOOTSTRAP_INPUT):
            return
        before = _require_private_file(BOOTSTRAP_INPUT, 0o600)
        try:
            current = os.lstat(BOOTSTRAP_INPUT)
            if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                raise FreshBootstrapError("bootstrap input authority changed")
            os.unlink(BOOTSTRAP_INPUT)
            host_state._fsync_directory(BOOTSTRAP_INPUT.parent)
        except OSError as error:
            raise FreshBootstrapError("bootstrap input consumption failed") from error

    def bootstrap_input_exists(self) -> bool:
        if not os.path.lexists(BOOTSTRAP_INPUT):
            return False
        try:
            _require_private_file(BOOTSTRAP_INPUT, 0o600)
            return True
        except (OSError, DeploymentError):
            return False

    def persist_candidate_images(self, candidate: FreshCandidateArtifacts) -> None:
        _replace_env_images(ENV_FILE, candidate.api_reference, candidate.web_reference)

    def _base_candidate(self, candidate: FreshCandidateArtifacts) -> CandidateArtifacts:
        if self._candidate is None:
            raise FreshBootstrapError("fresh candidate authority is unavailable")
        if self._candidate.revision != candidate.revision:
            raise FreshBootstrapError("fresh candidate authority changed")
        return self._candidate

    def _project_resources(self) -> dict[str, list[str]]:
        labeled = {
            "containers": self._ids(
                [
                    str(DOCKER),
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"label=com.docker.compose.project={PROJECT_NAME}",
                ]
            ),
            "networks": self._ids(
                [
                    str(DOCKER),
                    "network",
                    "ls",
                    "--quiet",
                    "--filter",
                    f"label=com.docker.compose.project={PROJECT_NAME}",
                ]
            ),
            "volumes": self._ids(
                [
                    str(DOCKER),
                    "volume",
                    "ls",
                    "--quiet",
                    "--filter",
                    f"label=com.docker.compose.project={PROJECT_NAME}",
                ]
            ),
        }
        container_prefixes = (f"{PROJECT_NAME}-", f"{PROJECT_NAME}_")
        named_containers = [
            identifier
            for identifier, name in self._pairs(
                [str(DOCKER), "ps", "--all", "--format", "{{.ID}}|{{.Names}}"]
            )
            if name.startswith(container_prefixes)
        ]
        named_networks = [
            identifier
            for identifier, name in self._pairs(
                [str(DOCKER), "network", "ls", "--format", "{{.ID}}|{{.Name}}"]
            )
            if name in EXPECTED_NETWORKS
        ]
        named_volumes = [
            name
            for name in self._ids(
                [str(DOCKER), "volume", "ls", "--format", "{{.Name}}"]
            )
            if name in EXPECTED_VOLUMES
        ]
        return {
            "containers": sorted(set(labeled["containers"] + named_containers)),
            "networks": sorted(set(labeled["networks"] + named_networks)),
            "volumes": sorted(set(labeled["volumes"] + named_volumes)),
        }

    def _ids(self, arguments: list[str]) -> list[str]:
        result = self._run(arguments).stdout.decode("utf-8").splitlines()
        if any(not value or any(character.isspace() for character in value) for value in result):
            raise FreshBootstrapError("production resource identity is invalid")
        return result

    def _pairs(self, arguments: list[str]) -> list[tuple[str, str]]:
        rows = self._run(arguments).stdout.decode("utf-8").splitlines()
        parsed = [row.split("|") for row in rows]
        if any(
            len(row) != 2
            or not row[0]
            or not row[1]
            or any(character.isspace() for value in row for character in value)
            for row in parsed
        ):
            raise FreshBootstrapError("production resource identity is invalid")
        return [(row[0], row[1]) for row in parsed]

    def _validate_recovery_resources(self, resources: dict[str, list[str]]) -> None:
        for container in resources["containers"]:
            value = self._inspect_one([str(DOCKER), "inspect", container])
            labels = value.get("Config", {}).get("Labels", {})
            if (
                labels.get("com.docker.compose.project") != PROJECT_NAME
                or labels.get("com.docker.compose.service") not in ALLOWED_SERVICES
            ):
                raise FreshBootstrapError("recovery container authority differs")
        for kind, expected in (("network", EXPECTED_NETWORKS), ("volume", EXPECTED_VOLUMES)):
            for identifier in resources[f"{kind}s"]:
                value = self._inspect_one([str(DOCKER), kind, "inspect", identifier])
                labels = value.get("Labels", {})
                if (
                    value.get("Name") not in expected
                    or labels.get("com.docker.compose.project") != PROJECT_NAME
                ):
                    raise FreshBootstrapError(f"recovery {kind} authority differs")

    def _inspect_one(self, arguments: list[str]) -> dict[str, object]:
        try:
            value = json.loads(self._run(arguments).stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FreshBootstrapError("production resource metadata is invalid") from error
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise FreshBootstrapError("production resource metadata is invalid")
        return value[0]


def _validate_ingress_source() -> None:
    expected = BOOTSTRAP_INGRESS_ROOT / "scripts" / "host_tools" / Path(__file__).name
    actual = Path(__file__).resolve(strict=True)
    expected_resolved = expected.resolve(strict=True)
    actual_stat = os.lstat(actual)
    expected_stat = os.lstat(expected_resolved)
    if (
        actual != expected_resolved
        or (actual_stat.st_dev, actual_stat.st_ino)
        != (expected_stat.st_dev, expected_stat.st_ino)
        or not stat.S_ISREG(actual_stat.st_mode)
        or actual_stat.st_nlink != 1
    ):
        raise FreshBootstrapError("fresh bootstrap worker source is untrusted")
    host_state.release_content_sha256(BOOTSTRAP_INGRESS_ROOT)


def _require_disjoint_authorities() -> None:
    values = (
        BOOTSTRAP_INGRESS_ROOT.resolve(strict=True),
        ENV_FILE.resolve(strict=True),
        BACKUP_DIRECTORY.resolve(strict=True),
    )
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                raise FreshBootstrapError("fresh bootstrap authorities overlap")
    if os.path.lexists(BOOTSTRAP_INPUT):
        input_path = BOOTSTRAP_INPUT.resolve(strict=True)
        if input_path.is_relative_to(BOOTSTRAP_INGRESS_ROOT) or input_path.is_relative_to(
            BACKUP_DIRECTORY
        ):
            raise FreshBootstrapError("fresh bootstrap input authority overlaps")


def main() -> int:
    from scripts.host_tools.fresh_host_bootstrap import (
        FreshBootstrapInterventionRequired,
        _zeroize,
        read_token,
        run_fresh_bootstrap,
    )

    token: bytearray | None = None
    try:
        command = os.environ.get("SSH_ORIGINAL_COMMAND")
        if command is None:
            raise FreshBootstrapError("restricted bootstrap command is unavailable")
        FreshBootstrapRequest.from_command(command)
        token = read_token(sys.stdin.buffer.read(8 * 1024 + 2))
        paths = host_state.production_paths()
        host_state.initialize_layout(paths)
        result = run_fresh_bootstrap(
            command,
            token,
            paths=paths,
            adapter=ProductionFreshBootstrapAdapter(paths),
            clock=lambda: dt.datetime.now(dt.timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
        )
        print(json.dumps({"status": result.status}, separators=(",", ":")))
        return 0
    except (
        FreshBootstrapError,
        FreshBootstrapInterventionRequired,
        host_state.ContractError,
        OSError,
    ):
        print("fresh host bootstrap contract failed", file=sys.stderr)
        return 1
    finally:
        if token is not None:
            _zeroize(token)


if __name__ == "__main__":
    raise SystemExit(main())
