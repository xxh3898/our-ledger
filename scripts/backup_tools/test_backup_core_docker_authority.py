from __future__ import annotations

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKUP_CORE = ROOT / "scripts" / "backup_tools" / "backup_core.sh"
PRODUCTION_DEPLOY = ROOT / "scripts" / "host_tools" / "production_deploy.py"
DARWIN_DOCKER = "/usr/local/bin/docker"
LINUX_DOCKER = "/usr/bin/docker"
UNAME_COMMAND = "/usr/bin/uname -s"


class BackupCoreDockerAuthorityTest(unittest.TestCase):
    def test_static_contract_uses_only_fixed_absolute_docker_authority(self) -> None:
        source = BACKUP_CORE.read_text(encoding="utf-8")

        self.assertEqual(source.count(UNAME_COMMAND), 1)
        self.assertRegex(
            source,
            re.compile(r'Darwin\)\s+DOCKER="/usr/local/bin/docker"'),
        )
        self.assertRegex(
            source,
            re.compile(r'Linux\)\s+DOCKER="/usr/bin/docker"'),
        )
        self.assertIn('"$DOCKER" compose version', source)
        self.assertIn('"$DOCKER" compose', source)
        self.assertIn('"$DOCKER" inspect', source)
        self.assertNotIn("command -v docker", source)
        self.assertNotIn("which docker", source)
        self.assertNotIn("DOCKER_BIN", source)
        self.assertNotRegex(source, re.compile(r"(?m)^\s*docker (?:compose|inspect)\b"))

        deployment_source = PRODUCTION_DEPLOY.read_text(encoding="utf-8")
        deployment_match = re.search(
            r'^DOCKER = Path\("([^\"]+)"\)$',
            deployment_source,
            re.MULTILINE,
        )
        darwin_match = re.search(
            r'Darwin\)\s+DOCKER="([^\"]+)"',
            source,
        )
        self.assertIsNotNone(deployment_match)
        self.assertIsNotNone(darwin_match)
        self.assertEqual(darwin_match.group(1), deployment_match.group(1))

    def test_darwin_and_linux_use_selected_absolute_docker_only(self) -> None:
        for platform in ("Darwin", "Linux"):
            with self.subTest(platform=platform):
                result = self._run_harness(platform=platform, fixed_kind="valid")

                self.assertEqual(result.completed.returncode, 1)
                self.assertFalse(result.attacker_capture.exists())
                invocations = result.selected_capture.read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(len(invocations), 4)
                self.assertEqual(invocations[0], "compose version")
                self.assertTrue(any(" config --quiet" in value for value in invocations))
                self.assertTrue(
                    any(" ps --all --quiet postgres" in value for value in invocations)
                )
                self.assertTrue(any(value.startswith("inspect ") for value in invocations))

    def test_unsupported_platform_fails_before_docker_execution(self) -> None:
        result = self._run_harness(platform="Unsupported", fixed_kind="valid")

        self.assertEqual(result.completed.returncode, 1)
        self.assertFalse(result.selected_capture.exists())
        self.assertFalse(result.attacker_capture.exists())

    def test_missing_and_nonexecutable_fixed_docker_fail_closed(self) -> None:
        for fixed_kind in ("missing", "nonexecutable"):
            with self.subTest(fixed_kind=fixed_kind):
                result = self._run_harness(platform="Darwin", fixed_kind=fixed_kind)

                self.assertEqual(result.completed.returncode, 1)
                self.assertFalse(result.selected_capture.exists())
                self.assertFalse(result.attacker_capture.exists())

    def test_compose_plugin_unavailable_fails_closed(self) -> None:
        result = self._run_harness(
            platform="Linux",
            fixed_kind="valid",
            compose_version_exit=67,
        )

        self.assertEqual(result.completed.returncode, 1)
        self.assertEqual(
            result.selected_capture.read_text(encoding="utf-8").splitlines(),
            ["compose version"],
        )
        self.assertFalse(result.attacker_capture.exists())

    def _run_harness(
        self,
        *,
        platform: str,
        fixed_kind: str,
        compose_version_exit: int = 0,
    ) -> HarnessResult:
        temporary_context = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_context.cleanup)
        temporary = Path(temporary_context.name).resolve()
        repository = temporary / "repository"
        tools = repository / "scripts" / "backup_tools"
        tools.mkdir(parents=True, mode=0o700)
        (repository / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

        selected = temporary / "selected-docker"
        selected_capture = temporary / "selected-invocations"
        attacker_directory = temporary / "attacker-bin"
        attacker_directory.mkdir(mode=0o700)
        attacker = attacker_directory / "docker"
        attacker_capture = temporary / "attacker-invocations"
        attacker.write_text(
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'printf "%s\\n" "$*" >> "$ATTACKER_CAPTURE"\n'
            "exit 91\n",
            encoding="utf-8",
        )
        attacker.chmod(0o700)

        if fixed_kind != "missing":
            selected.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/bash
                    set -euo pipefail
                    printf '%s\n' "$*" >> "$SELECTED_CAPTURE"
                    if [[ "$1" == compose && "$2" == version ]]; then
                      exit "${COMPOSE_VERSION_EXIT:-0}"
                    fi
                    if [[ "$1" == compose && "$*" == *" config --quiet" ]]; then
                      exit 0
                    fi
                    if [[ "$1" == compose && "$*" == *" ps --all --quiet postgres" ]]; then
                      printf '%s\n' synthetic-postgres
                      exit 0
                    fi
                    if [[ "$1" == inspect ]]; then
                      printf '%s\n' '[]'
                      exit 0
                    fi
                    exit 92
                    """
                ),
                encoding="utf-8",
            )
            selected.chmod(0o700 if fixed_kind == "valid" else 0o600)

        helper = tools / "backup_artifact.py"
        helper.write_text(
            textwrap.dedent(
                """\
                import sys

                command = sys.argv[1]
                if command in {"validate-env", "validate-backup-dir"}:
                    print(sys.argv[sys.argv.index("--path") + 1])
                    raise SystemExit(0)
                if command == "check-container":
                    sys.stdin.read()
                    raise SystemExit(1)
                raise SystemExit(93)
                """
            ),
            encoding="utf-8",
        )
        helper.chmod(0o600)

        source = BACKUP_CORE.read_text(encoding="utf-8")
        self.assertEqual(source.count(UNAME_COMMAND), 1)
        source = source.replace(
            UNAME_COMMAND,
            f"/usr/bin/printf '%s\\n' {platform}",
            1,
        )
        if platform in {"Darwin", "Linux"}:
            selected_literal = DARWIN_DOCKER if platform == "Darwin" else LINUX_DOCKER
            self.assertEqual(source.count(selected_literal), 1)
            source = source.replace(selected_literal, str(selected), 1)

        harness = tools / "backup_core.sh"
        harness.write_text(source, encoding="utf-8")
        harness.chmod(0o700)

        external = temporary / "external"
        external.mkdir(mode=0o700)
        env_file = external / "production.env"
        env_file.write_text("SYNTHETIC=1\n", encoding="utf-8")
        env_file.chmod(0o600)
        backup_directory = external / "backups"
        backup_directory.mkdir(mode=0o700)

        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{attacker_directory}:/usr/bin:/bin:/usr/sbin:/sbin",
                "DOCKER_BIN": str(attacker),
                "ATTACKER_CAPTURE": str(attacker_capture),
                "SELECTED_CAPTURE": str(selected_capture),
                "COMPOSE_VERSION_EXIT": str(compose_version_exit),
            }
        )
        completed = subprocess.run(
            [
                "/bin/bash",
                str(harness),
                "--project-name",
                "synthetic-production",
                "--env-file",
                str(env_file),
                "--backup-dir",
                str(backup_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=10,
        )
        return HarnessResult(
            completed=completed,
            selected_capture=selected_capture,
            attacker_capture=attacker_capture,
        )


class HarnessResult:
    def __init__(
        self,
        *,
        completed: subprocess.CompletedProcess[str],
        selected_capture: Path,
        attacker_capture: Path,
    ) -> None:
        self.completed = completed
        self.selected_capture = selected_capture
        self.attacker_capture = attacker_capture


if __name__ == "__main__":
    unittest.main()
