from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Mapping, Sequence

from scripts.backup_tools import backup_artifact
from scripts.host_tools import host_state
from scripts.host_tools.deploy_transaction import (
    API_REPOSITORY,
    DeploymentError,
    WEB_REPOSITORY,
)
from scripts.host_tools.fresh_host_bootstrap import (
    FreshBootstrapError,
    FreshBootstrapRequest,
    FreshCandidateArtifacts,
)
from scripts.host_tools.host_state import HostPaths, OperationLock, SchemaAuthority
from scripts.host_tools.production_deploy import (
    SCHEMA_QUERY,
    _extract_verified_runtime,
    _read_private_bytes,
    _replace_env_images,
    _require_private_directory,
    _require_private_file,
)


MAX_OUTPUT = 1024 * 1024


class SyntheticFreshBootstrapAdapter:
    """Disposable Docker adapter used only by the Issue #53 verification gate."""

    def __init__(
        self,
        *,
        paths: HostPaths,
        env_file: Path,
        input_file: Path,
        backup_directory: Path,
        project_name: str,
        revision: str,
        api_image: str,
        web_image: str,
        runtime_image: str,
        runtime_digest: str,
        loopback_port: int,
    ):
        self.paths = paths
        self.env_file = env_file
        self.input_file = input_file
        self.backup_directory = backup_directory
        self.project_name = project_name
        self.revision = revision
        self.api_image = api_image
        self.web_image = web_image
        self.runtime_image = runtime_image
        self.runtime_digest = runtime_digest
        self.loopback_port = loopback_port
        self._temporary_root: Path | None = None
        self._runtime_container: str | None = None
        self._runtime_source: Path | None = None

    def validate_authority(self) -> None:
        _require_private_file(self.env_file, 0o600)
        _require_private_directory(self.backup_directory, 0o700)
        if self.paths.app_root.is_relative_to(Path.cwd()) or Path.cwd().is_relative_to(
            self.paths.app_root
        ):
            raise FreshBootstrapError("synthetic host overlaps repository")
        backup_artifact.validate_backup_directory_read_only(
            str(Path.cwd()), str(self.backup_directory)
        )

    def validate_resource_authority(self, *, recovering: bool) -> None:
        if os.path.lexists(self.input_file):
            _require_private_file(self.input_file, 0o600)
            _read_private_bytes(self.input_file, 0o600, 8 * 1024)
        elif not recovering:
            raise FreshBootstrapError("synthetic bootstrap input is unavailable")
        resources = self._resource_ids()
        if not recovering and any(resources.values()):
            raise FreshBootstrapError("synthetic project resources already exist")
        for identifiers in resources.values():
            for identifier in identifiers:
                self._require_cleanup_labels(identifier)

    def prepare_artifacts(
        self,
        request: FreshBootstrapRequest,
        token: bytearray,
    ) -> FreshCandidateArtifacts:
        if request.revision != self.revision or request.runtime_config_digest != self.runtime_digest:
            raise FreshBootstrapError("synthetic candidate request differs")
        self._validate_image(self.api_image, request.revision)
        self._validate_image(self.web_image, request.revision)
        self._validate_image(self.runtime_image, request.revision)
        self._temporary_root = Path(
            tempfile.mkdtemp(prefix="our-ledger-fresh-runtime-")
        ).resolve(strict=True)
        self._temporary_root.chmod(0o700)
        archive = self._temporary_root / "runtime.tar"
        source = self._temporary_root / "runtime"
        self._runtime_container = f"our-ledger-fresh-runtime-{uuid.uuid4().hex}"
        self._run(
            [
                "docker",
                "create",
                "--name",
                self._runtime_container,
                self.runtime_image,
            ]
        )
        self._run(
            [
                "docker",
                "export",
                "--output",
                str(archive),
                self._runtime_container,
            ]
        )
        _extract_verified_runtime(archive, source)
        self._runtime_source = source
        return FreshCandidateArtifacts(
            revision=request.revision,
            api_reference=f"{API_REPOSITORY}:{request.revision}",
            web_reference=f"{WEB_REPOSITORY}:{request.revision}",
            runtime_config_digest=request.runtime_config_digest,
            runtime_config_revision=request.revision,
            runtime_source=source,
        )

    def start_postgres(self, candidate: FreshCandidateArtifacts) -> None:
        self._run(self._compose(candidate, ["up", "--detach", "--wait", "postgres"]))

    def postgres_is_ready(self, candidate: FreshCandidateArtifacts) -> bool:
        return self._service_is_healthy(candidate, "postgres")

    def run_migration(self, candidate: FreshCandidateArtifacts) -> None:
        result = self._run(
            self._compose(
                candidate,
                ["--profile", "migration", "run", "--rm", "--no-deps", "api-migration"],
            ),
            timeout=600,
        )
        if result.stdout.decode("utf-8", errors="replace").splitlines().count(
            "migration-validation: success"
        ) != 1:
            raise FreshBootstrapError("synthetic migration marker differs")

    def read_schema_authority(self) -> SchemaAuthority:
        candidate = self._candidate()
        result = self._run(
            self._compose(
                candidate,
                ["exec", "-T", "postgres", "sh", "-ceu", SCHEMA_QUERY],
            )
        )
        rows = [line for line in result.stdout.decode("utf-8").splitlines() if line]
        parsed = [line.split("|") for line in rows]
        if not rows or any(len(row) != 8 for row in parsed):
            raise FreshBootstrapError("synthetic Flyway history differs")
        failed = sum(1 for row in parsed if row[7] != "t")
        versions = [row[1] for row in parsed if row[7] == "t" and row[1]]
        if failed or not versions:
            raise FreshBootstrapError("synthetic Flyway state is invalid")
        return SchemaAuthority(
            versions[-1],
            failed,
            hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest(),
        )

    def run_household_bootstrap(self, candidate: FreshCandidateArtifacts) -> str:
        payload = bytearray(_read_private_bytes(self.input_file, 0o600, 8 * 1024))
        try:
            result = self._run(
                self._compose(
                    candidate,
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
                timeout=600,
            )
        finally:
            for index in range(len(payload)):
                payload[index] = 0
            payload.clear()
        lines = result.stdout.decode("utf-8", errors="replace").splitlines()
        matches = [
            value
            for value in ("created", "verified")
            if lines.count(f"household-bootstrap: {value}") == 1
        ]
        if len(matches) != 1:
            raise FreshBootstrapError("synthetic household marker differs")
        return matches[0]

    def household_bootstrap_is_exact(self) -> bool:
        sql = (
            "SELECT (SELECT COUNT(*) FROM users) || ':' || "
            "(SELECT COUNT(*) FROM households) || ':' || "
            "(SELECT COUNT(*) FROM household_members) || ':' || "
            "(SELECT string_agg(role, ',' ORDER BY role) FROM household_members) || ':' || "
            "(SELECT base_currency || ':' || timezone FROM households)"
        )
        try:
            result = self._run(
                self._compose(
                    self._candidate(),
                    [
                        "exec",
                        "-T",
                        "postgres",
                        "sh",
                        "-ceu",
                        'exec psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" '
                        "--tuples-only --no-align --set ON_ERROR_STOP=1 --command \"$1\"",
                        "sh",
                        sql,
                    ],
                )
            )
            return result.stdout.decode("utf-8").strip() == (
                "2:1:2:MEMBER,OWNER:KRW:Asia/Seoul"
            )
        except (FreshBootstrapError, UnicodeDecodeError):
            return False

    def start_application(self, candidate: FreshCandidateArtifacts) -> None:
        self._run(
            self._compose(
                candidate,
                [
                    "up",
                    "--detach",
                    "--no-build",
                    "--pull",
                    "never",
                    "--wait",
                    "--wait-timeout",
                    "180",
                    "api",
                    "web",
                ],
            ),
            timeout=240,
        )

    def candidate_is_ready(self, candidate: FreshCandidateArtifacts) -> bool:
        if not all(
            self._service_is_healthy(candidate, service)
            for service in ("postgres", "api", "web")
        ):
            return False
        return self._status("/healthz") == 200 and self._status("/api/v1/me") == 401

    def run_verified_backup(self, lock: OperationLock) -> str:
        lock.assert_held(self.paths)
        identity = self._candidate_identity()
        core = (
            self.paths.releases
            / identity.release_name
            / "scripts"
            / "backup_tools"
            / "backup_core.sh"
        )
        self._run(
            [
                "/bin/bash",
                str(core),
                "--project-name",
                self.project_name,
                "--env-file",
                str(self.env_file),
                "--backup-dir",
                str(self.backup_directory),
            ],
            timeout=600,
        )
        marker = self.backup_directory / "last-success.json"
        return hashlib.sha256(_read_private_bytes(marker, 0o600, 16 * 1024)).hexdigest()

    def backup_marker_is_verified(self, marker_sha256: str) -> bool:
        try:
            marker = self.backup_directory / "last-success.json"
            return (
                hashlib.sha256(_read_private_bytes(marker, 0o600, 16 * 1024)).hexdigest()
                == marker_sha256
                and backup_artifact.inventory(self.backup_directory)["lastSuccessValid"]
            )
        except (
            OSError,
            FreshBootstrapError,
            DeploymentError,
            backup_artifact.ContractError,
        ):
            return False

    def consume_bootstrap_input(self) -> None:
        if not os.path.lexists(self.input_file):
            return
        before = _require_private_file(self.input_file, 0o600)
        current = os.lstat(self.input_file)
        if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
            raise FreshBootstrapError("synthetic input authority changed")
        os.unlink(self.input_file)
        host_state._fsync_directory(self.input_file.parent)

    def bootstrap_input_exists(self) -> bool:
        if not os.path.lexists(self.input_file):
            return False
        try:
            _require_private_file(self.input_file, 0o600)
            return True
        except (OSError, FreshBootstrapError, DeploymentError):
            return False

    def persist_candidate_images(self, candidate: FreshCandidateArtifacts) -> None:
        _replace_env_images(self.env_file, candidate.api_reference, candidate.web_reference)

    def cleanup(self) -> None:
        failed = False
        if self._runtime_container is not None:
            result = subprocess.run(
                ["docker", "rm", "--force", self._runtime_container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
            )
            failed = result.returncode != 0
        if self._temporary_root is not None and self._temporary_root.exists():
            shutil.rmtree(self._temporary_root)
        self._runtime_container = None
        self._temporary_root = None
        self._runtime_source = None
        if failed:
            raise FreshBootstrapError("synthetic runtime cleanup failed")

    def _candidate(self) -> FreshCandidateArtifacts:
        return FreshCandidateArtifacts(
            revision=self.revision,
            api_reference=f"{API_REPOSITORY}:{self.revision}",
            web_reference=f"{WEB_REPOSITORY}:{self.revision}",
            runtime_config_digest=self.runtime_digest,
            runtime_config_revision=self.revision,
            runtime_source=self.paths.releases / self.runtime_digest.removeprefix("sha256:"),
        )

    def _candidate_identity(self) -> host_state.ReleaseIdentity:
        release = self.paths.releases / self.runtime_digest.removeprefix("sha256:")
        return host_state.ReleaseIdentity(
            self.revision,
            self.runtime_digest,
            self.revision,
            host_state.release_content_sha256(release),
        )

    def _compose(
        self,
        candidate: FreshCandidateArtifacts,
        tail: Sequence[str],
    ) -> list[str]:
        release = self.paths.releases / candidate.runtime_config_digest.removeprefix(
            "sha256:"
        )
        return [
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "--project-directory",
            str(release),
            "--env-file",
            str(self.env_file),
            "--file",
            str(release / "compose.yaml"),
            *tail,
        ]

    def _service_is_healthy(
        self,
        candidate: FreshCandidateArtifacts,
        service: str,
    ) -> bool:
        try:
            identifier = self._run(
                self._compose(candidate, ["ps", "--all", "--quiet", service])
            ).stdout.decode("utf-8").strip()
            if not identifier or "\n" in identifier:
                return False
            value = json.loads(self._run(["docker", "inspect", identifier]).stdout)
            if not isinstance(value, list) or len(value) != 1:
                return False
            labels = value[0].get("Config", {}).get("Labels", {})
            expected_image = {
                "api": candidate.api_reference,
                "web": candidate.web_reference,
            }.get(service)
            return (
                value[0].get("State", {}).get("Health", {}).get("Status") == "healthy"
                and labels.get("com.docker.compose.project") == self.project_name
                and labels.get("com.docker.compose.service") == service
                and (expected_image is None or value[0].get("Config", {}).get("Image") == expected_image)
            )
        except (FreshBootstrapError, UnicodeDecodeError, json.JSONDecodeError):
            return False

    def _validate_image(self, reference: str, revision: str) -> None:
        try:
            values = json.loads(self._run(["docker", "image", "inspect", reference]).stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FreshBootstrapError("synthetic image metadata is invalid") from error
        if not isinstance(values, list) or len(values) != 1:
            raise FreshBootstrapError("synthetic image metadata is invalid")
        labels = values[0].get("Config", {}).get("Labels", {})
        if (
            values[0].get("Os") != "linux"
            or labels.get("org.opencontainers.image.revision") != revision
            or labels.get("org.opencontainers.image.version") != revision
            or labels.get("org.opencontainers.image.source")
            != "https://github.com/xxh3898/our-ledger"
        ):
            raise FreshBootstrapError("synthetic image identity differs")

    def _resource_ids(self) -> dict[str, list[str]]:
        filters = ["--filter", f"label=com.docker.compose.project={self.project_name}"]
        return {
            "containers": self._lines(["docker", "ps", "--all", "--quiet", *filters]),
            "networks": self._lines(["docker", "network", "ls", "--quiet", *filters]),
            "volumes": self._lines(["docker", "volume", "ls", "--quiet", *filters]),
        }

    def _require_cleanup_labels(self, identifier: str) -> None:
        values = json.loads(self._run(["docker", "inspect", identifier]).stdout)
        if not isinstance(values, list) or len(values) != 1:
            raise FreshBootstrapError("synthetic resource metadata differs")
        labels = values[0].get("Config", {}).get("Labels") or values[0].get("Labels", {})
        expected = {
            "io.homeserver.cleanup.environment": "development",
            "io.homeserver.cleanup.project": "our-ledger",
            "io.homeserver.cleanup.task": "issue-53-fresh-host-bootstrap",
            "io.homeserver.cleanup.lifecycle": "task",
            "io.homeserver.cleanup.retain": "false",
            "io.homeserver.cleanup.git-head": self.revision,
        }
        if any(labels.get(key) != value for key, value in expected.items()):
            raise FreshBootstrapError("synthetic cleanup labels differ")

    def _lines(self, arguments: list[str]) -> list[str]:
        return [line for line in self._run(arguments).stdout.decode("utf-8").splitlines() if line]

    def _status(self, path: str) -> int:
        connection = http.client.HTTPConnection("127.0.0.1", self.loopback_port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            response.read(1024)
            return response.status
        except OSError:
            return 0
        finally:
            connection.close()

    def _run(
        self,
        arguments: Sequence[str],
        *,
        input_bytes: bytes | None = None,
        timeout: int = 240,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            result = subprocess.run(
                list(arguments),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
                timeout=timeout,
                env=dict(environment) if environment is not None else None,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FreshBootstrapError("synthetic fixed command failed") from error
        if len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT:
            raise FreshBootstrapError("synthetic command output exceeded bound")
        if result.returncode != 0:
            raise FreshBootstrapError("synthetic fixed command failed")
        return result
