from __future__ import annotations

import json
import os
import plistlib
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKUP_SOURCE = ROOT / "scripts" / "backup-our-ledger-bootstrap.sh"
OFFSITE_SOURCE = ROOT / "scripts" / "offsite-our-ledger-bootstrap.sh"
BACKUP_TARGET = (
    "/Users/homeserver/Server/apps/our-ledger/runtime-config/current/"
    "scripts/backup-production.sh"
)
OFFSITE_TARGET = (
    "/Users/homeserver/Server/apps/our-ledger/runtime-config/current/"
    "scripts/offsite-backup-production.sh"
)
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
EXPECTED_ENVIRONMENT = {
    "HOME": "/Users/homeserver",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": SYSTEM_PATH,
}
BACKUP_ARGUMENTS = [
    "--project-name",
    "our-ledger-production",
    "--env-file",
    "/Users/homeserver/Server/apps/our-ledger/.env",
    "--backup-dir",
    "/Users/homeserver/Server/backups/our-ledger/data",
]


class FixedBootstrapTest(unittest.TestCase):
    def test_static_contract_is_exact_and_secret_free(self) -> None:
        contracts = {
            BACKUP_SOURCE: (BACKUP_TARGET, '[[ "$#" -ne 0 ]]'),
            OFFSITE_SOURCE: (OFFSITE_TARGET, '[[ "$#" -ne 1 || "$1" != run ]]'),
        }

        for source_path, (target, interface) in contracts.items():
            with self.subTest(source=source_path.name):
                source = source_path.read_text(encoding="utf-8")
                self.assertEqual(source.splitlines()[0], "#!/bin/bash")
                self.assertIn("set -euo pipefail", source)
                self.assertIn("umask 077", source)
                self.assertIn(interface, source)
                self.assertEqual(source.count(target), 1)
                self.assertEqual(source.count("exec /usr/bin/env -i"), 1)
                self.assertIn("HOME=/Users/homeserver", source)
                self.assertIn("LANG=C", source)
                self.assertIn("LC_ALL=C", source)
                self.assertIn(f"PATH={SYSTEM_PATH}", source)
                self.assertIn('[[ ! -f "$ENTRYPOINT"', source)
                self.assertIn('-L "$ENTRYPOINT"', source)
                self.assertIn('! -O "$ENTRYPOINT"', source)
                self.assertIn('! -x "$ENTRYPOINT"', source)
                self.assertNotIn("/usr/local/bin", source)
                self.assertNotIn("/opt/homebrew/bin", source)
                self.assertNotRegex(
                    source,
                    re.compile(
                        r"(?m)(?:^|[;&|\s])(?:eval|source|curl|wget|ssh|scp|"
                        r"rsync|sudo|launchctl|docker|psql|rm|mv|cp|find|git)(?=[;&|\s]|$)"
                    ),
                )
                self.assertNotRegex(
                    source,
                    re.compile(
                        r"(?i)(?:password|token|secret|AGE_RECIPIENT|AGE-SECRET-KEY|"
                        r"private[ _-]?identity|cloudflare|database_url)"
                    ),
                )
                self.assertNotIn("Workspace", source)
                self.assertNotIn("${", source)
                self.assertNotIn("retry", source.lower())
                self.assertTrue(source_path.stat().st_mode & stat.S_IXUSR)

        backup = BACKUP_SOURCE.read_text(encoding="utf-8")
        for argument in BACKUP_ARGUMENTS:
            self.assertEqual(backup.count(argument), 1)

    def test_backup_sanitizes_environment_and_forwards_fixed_authority(self) -> None:
        result = self._run_synthetic(BACKUP_SOURCE, BACKUP_TARGET, [])

        self.assertEqual(result["arguments"], BACKUP_ARGUMENTS)
        self._assert_sanitized_environment(result["environment"])
        self.assertEqual(result["umask"], "077")

    def test_offsite_sanitizes_environment_and_forwards_exact_run(self) -> None:
        result = self._run_synthetic(OFFSITE_SOURCE, OFFSITE_TARGET, ["run"])

        self.assertEqual(result["arguments"], ["run"])
        self._assert_sanitized_environment(result["environment"])
        self.assertEqual(result["umask"], "077")

    def test_invalid_public_interfaces_fail_before_target_execution(self) -> None:
        invalid = (
            (BACKUP_SOURCE, BACKUP_TARGET, ["extra"]),
            (OFFSITE_SOURCE, OFFSITE_TARGET, []),
            (OFFSITE_SOURCE, OFFSITE_TARGET, ["status"]),
            (OFFSITE_SOURCE, OFFSITE_TARGET, ["run", "extra"]),
        )

        for source_path, target, arguments in invalid:
            with self.subTest(source=source_path.name, arguments=arguments):
                completed, payload = self._invoke_synthetic(
                    source_path,
                    target,
                    arguments,
                    target_kind="valid",
                )
                self.assertEqual(completed.returncode, 64)
                self.assertIsNone(payload)

    def test_missing_symlink_and_nonexecutable_targets_fail_closed(self) -> None:
        cases = ("missing", "symlink", "nonexecutable")

        for source_path, target, arguments in (
            (BACKUP_SOURCE, BACKUP_TARGET, []),
            (OFFSITE_SOURCE, OFFSITE_TARGET, ["run"]),
        ):
            for target_kind in cases:
                with self.subTest(source=source_path.name, target_kind=target_kind):
                    completed, payload = self._invoke_synthetic(
                        source_path,
                        target,
                        arguments,
                        target_kind=target_kind,
                    )
                    self.assertEqual(completed.returncode, 1)
                    self.assertIsNone(payload)

    def test_launchd_examples_match_fixed_paths_and_calendar_contract(self) -> None:
        backup = plistlib.loads(
            (ROOT / "launchd/com.homeserver.our-ledger-backup.plist.example").read_bytes()
        )
        offsite = plistlib.loads(
            (ROOT / "launchd/com.homeserver.our-ledger-offsite.plist.example").read_bytes()
        )

        self.assertEqual(
            backup["ProgramArguments"],
            ["/Users/homeserver/Server/scripts/backup/backup-our-ledger-bootstrap.sh"],
        )
        self.assertEqual(
            offsite["ProgramArguments"],
            [
                "/Users/homeserver/Server/scripts/offsite/offsite-our-ledger-bootstrap.sh",
                "run",
            ],
        )
        self.assertEqual(
            backup["StartCalendarInterval"],
            [{"Hour": hour, "Minute": 35} for hour in (0, 6, 12, 18)],
        )
        self.assertEqual(
            offsite["StartCalendarInterval"],
            [{"Hour": hour, "Minute": 50} for hour in (0, 6, 12, 18)],
        )
        for value in (backup, offsite):
            self.assertNotIn("KeepAlive", value)
            self.assertNotIn("RunAtLoad", value)
            self.assertNotIn("EnvironmentVariables", value)
            self.assertNotIn("WorkingDirectory", value)

    def _run_synthetic(
        self,
        source_path: Path,
        target_literal: str,
        arguments: list[str],
    ) -> dict[str, object]:
        completed, payload = self._invoke_synthetic(
            source_path,
            target_literal,
            arguments,
            target_kind="valid",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertIsNotNone(payload)
        return json.loads(payload)

    def _assert_sanitized_environment(self, environment: object) -> None:
        self.assertIsInstance(environment, dict)
        actual = environment
        for name, value in EXPECTED_ENVIRONMENT.items():
            self.assertEqual(actual.get(name), value)
        for name in (
            "AMBIENT_SECRET_MARKER",
            "BASH_ENV",
            "BASH_ENV_MARKER",
            "PYTHONPATH",
        ):
            self.assertNotIn(name, actual)

    def _invoke_synthetic(
        self,
        source_path: Path,
        target_literal: str,
        arguments: list[str],
        *,
        target_kind: str,
    ) -> tuple[subprocess.CompletedProcess[str], bytes | None]:
        with tempfile.TemporaryDirectory() as temporary_value:
            temporary = Path(temporary_value).resolve()
            capture = temporary / "capture.json"
            target = temporary / "runtime-entrypoint.py"
            actual_target = target
            if target_kind == "missing":
                actual_target = temporary / "missing-entrypoint"
            else:
                target.write_text(
                    "#!/usr/bin/python3\n"
                    "import json, os, sys\n"
                    "from pathlib import Path\n"
                    "current_umask = os.umask(0o077)\n"
                    "os.umask(current_umask)\n"
                    "payload = {\n"
                    "    'arguments': sys.argv[1:],\n"
                    "    'environment': dict(os.environ),\n"
                    "    'umask': f'{current_umask:03o}',\n"
                    "}\n"
                    f"Path({str(capture)!r}).write_text("
                    "json.dumps(payload, sort_keys=True), encoding='utf-8')\n",
                    encoding="utf-8",
                )
                target.chmod(0o700 if target_kind != "nonexecutable" else 0o600)
                if target_kind == "symlink":
                    link = temporary / "runtime-entrypoint-link"
                    link.symlink_to(target.name)
                    actual_target = link

            source = source_path.read_text(encoding="utf-8")
            self.assertEqual(source.count(target_literal), 1)
            harness = temporary / source_path.name
            harness.write_text(
                source.replace(target_literal, str(actual_target)),
                encoding="utf-8",
            )
            harness.chmod(0o700)
            bash_environment = temporary / "bash-environment.sh"
            bash_environment.write_text(
                "export BASH_ENV_MARKER=ambient\n"
                "export AMBIENT_SECRET_MARKER=must-not-reach-target\n",
                encoding="utf-8",
            )
            environment = {
                "HOME": "/attacker/home",
                "PATH": "/attacker/path",
                "PYTHONPATH": "/attacker/python",
                "BASH_ENV": str(bash_environment),
                "AMBIENT_SECRET_MARKER": "must-not-reach-target",
            }
            completed = subprocess.run(
                [str(harness), *arguments],
                cwd=temporary,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            payload = capture.read_bytes() if capture.exists() else None
            return completed, payload


if __name__ == "__main__":
    unittest.main()
