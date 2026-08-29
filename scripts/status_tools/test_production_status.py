#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.backup_tools import backup_artifact
from scripts.status_tools import production_status


CREATED_AT = "2026-08-29T03:15:00Z"
NOW = dt.datetime(2026, 8, 29, 3, 16, 0, tzinfo=dt.timezone.utc)


class FakeRunner:

    def __init__(
        self,
        project_name: str,
        compose_file: Path,
        *,
        service_payloads: dict[str, dict] | None = None,
        recurring_returncode: int = 0,
        recurring_body: dict | None = None,
    ) -> None:
        self.project_name = project_name
        self.compose_file = compose_file
        self.commands: list[list[str]] = []
        self.service_payloads = service_payloads or {
            service: container_payload(
                project_name,
                service,
                compose_file,
                restart_count=index,
            )
            for index, service in enumerate(("web", "api", "postgres"))
        }
        self.recurring_returncode = recurring_returncode
        self.recurring_body = recurring_body or recurring_health()

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        if command[-2:] == ["config", "--quiet"]:
            return completed(command)
        if "ps" in command:
            service = command[-1]
            payload = self.service_payloads.get(service)
            stdout = "" if payload is None else f"{service}-container\n"
            return completed(command, stdout=stdout)
        if command[:2] == ["docker", "inspect"]:
            service = command[-1].removesuffix("-container")
            return completed(
                command,
                stdout=json.dumps([self.service_payloads[service]]),
            )
        if command[:2] == ["docker", "exec"]:
            return completed(
                command,
                returncode=self.recurring_returncode,
                stdout=(
                    ""
                    if self.recurring_returncode
                    else "200\n" + json.dumps(self.recurring_body)
                ),
            )
        raise AssertionError(f"unexpected command: {command!r}")


def completed(
    command: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def container_payload(
    project_name: str,
    service: str,
    compose_file: Path,
    *,
    state: str = "running",
    health: str | None = "healthy",
    restart_count: int = 0,
) -> dict:
    host_config: dict = {"PortBindings": {}}
    if service == "web":
        host_config["PortBindings"] = {
            "8080/tcp": [
                {"HostIp": "127.0.0.1", "HostPort": "0"}
            ]
        }
    state_payload: dict = {"Status": state}
    if health is not None:
        state_payload["Health"] = {"Status": health}
    return {
        "Config": {
            "Env": [
                "POSTGRES_PASSWORD=must-not-leak",
                "OWNER_EMAIL=owner@example.test",
            ],
            "Labels": {
                "com.docker.compose.project": project_name,
                "com.docker.compose.service": service,
                "com.docker.compose.project.config_files": str(compose_file.resolve()),
            },
        },
        "HostConfig": host_config,
        "NetworkSettings": {
            "Ports": (
                {
                    "8080/tcp": [
                        {"HostIp": "127.0.0.1", "HostPort": "49152"}
                    ]
                }
                if service == "web"
                else {}
            )
        },
        "RestartCount": restart_count,
        "State": state_payload,
    }


def recurring_health(*, status: str = "UP") -> dict:
    return {
        "status": status,
        "components": {
            "recurringScheduler": {
                "status": status,
                "details": {
                    "enabled": True,
                    "processStartedAt": "2026-08-29T03:00:00Z",
                    "pollCountSinceStart": 10,
                    "lastPollStartedAt": "2026-08-29T03:15:30Z",
                    "lastPollCompletedAt": "2026-08-29T03:15:31Z",
                    "lastPollSucceeded": True,
                    "lastAdvancedOccurrenceCount": 2,
                    "lastPollRuleFailureCount": 1,
                    "totalRuleFailureCountSinceStart": 3,
                    "consecutivePollExecutionFailures": 0,
                    "lastPollExecutionFailureAt": None,
                    "lastRuleFailureAt": "2026-08-29T03:15:30Z",
                    "recurringId": 7001,
                    "email": "owner@example.test",
                    "amount": 900000,
                    "backupPath": "/private/sensitive/backups",
                },
            }
        },
    }


class ProductionStatusTest(unittest.TestCase):

    def setUp(self) -> None:
        self.temp_root = Path(
            tempfile.mkdtemp(prefix="our-ledger-status-unit.")
        ).resolve()
        self.temp_root.chmod(0o700)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.compose_file = self.repo_root / "compose.prod.yaml"
        self.env_file = self.temp_root / "production.env"
        self.env_file.write_text("SYNTHETIC=true\n", encoding="utf-8")
        self.env_file.chmod(0o600)
        self.backup_directory = self.temp_root / "backups"
        self.backup_directory.mkdir(mode=0o700)
        self.project_name = "our-ledger-status-test"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root)

    def test_should_collectExactPrivacySafeSnapshot_when_allSourcesAreAvailable(self) -> None:
        self.create_valid_bundle()
        (self.backup_directory / "invalid.backup").mkdir(mode=0o700)
        (self.backup_directory / ".synthetic.partial").mkdir(mode=0o700)
        foreign = self.backup_directory / "operator-note.txt"
        foreign.write_text("foreign", encoding="utf-8")
        foreign.chmod(0o600)
        runner = FakeRunner(self.project_name, self.compose_file)
        before = directory_fingerprint(self.backup_directory)

        snapshot = self.collect(runner)

        self.assertEqual(set(snapshot), {
            "formatVersion", "observedAt", "services", "origin",
            "recurring", "backup", "filesystem",
        })
        self.assertEqual(set(snapshot["services"]), {"web", "api", "postgres"})
        for service in snapshot["services"].values():
            self.assertEqual(set(service), {"state", "health", "restartCount"})
            self.assertEqual(service["state"], "RUNNING")
            self.assertEqual(service["health"], "HEALTHY")
        self.assertEqual(snapshot["origin"], {
            "reachable": True,
            "healthzStatus": 200,
        })
        self.assertEqual(set(snapshot["recurring"]), {
            "reachable", "status", "enabled", "processStartedAt",
            "pollCountSinceStart", "lastPollStartedAt", "lastPollCompletedAt",
            "lastPollSucceeded", "lastAdvancedOccurrenceCount",
            "lastPollRuleFailureCount", "totalRuleFailureCountSinceStart",
            "consecutivePollExecutionFailures", "lastPollExecutionFailureAt",
            "lastRuleFailureAt",
        })
        self.assertTrue(snapshot["recurring"]["reachable"])
        self.assertEqual(snapshot["recurring"]["status"], "UP")
        self.assertEqual(snapshot["recurring"]["lastPollRuleFailureCount"], 1)
        self.assertEqual(snapshot["backup"]["markerState"], "VALID")
        self.assertEqual(snapshot["backup"]["ageSeconds"], 60)
        self.assertEqual(snapshot["backup"]["schemaVersion"], "8")
        self.assertEqual(snapshot["backup"]["inventory"], {
            "valid": 1,
            "invalid": 1,
            "incomplete": 1,
            "foreign": 1,
        })
        self.assertEqual(snapshot["filesystem"], {
            "state": "AVAILABLE",
            "capacityBytes": 1_000_000,
            "availableBytes": 400_000,
            "usedPercent": 60.0,
        })
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for forbidden in (
            "must-not-leak",
            "owner@example.test",
            "900000",
            "/private/sensitive",
            str(self.backup_directory),
            "operator-note.txt",
            ".backup",
            "sha256",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(directory_fingerprint(self.backup_directory), before)
        self.assert_commands_are_read_only(runner.commands)

    def test_should_reportStoppedMissingAndUnreachable_withoutFalseSuccess(self) -> None:
        payloads = {
            "web": container_payload(
                self.project_name,
                "web",
                self.compose_file,
                state="exited",
                health="unhealthy",
            ),
            "api": container_payload(
                self.project_name,
                "api",
                self.compose_file,
                health="unhealthy",
            ),
        }
        runner = FakeRunner(
            self.project_name,
            self.compose_file,
            service_payloads=payloads,
            recurring_returncode=1,
        )

        snapshot = self.collect(runner)

        self.assertEqual(snapshot["services"]["web"], {
            "state": "EXITED", "health": "UNHEALTHY", "restartCount": 0,
        })
        self.assertEqual(snapshot["services"]["postgres"], {
            "state": "MISSING", "health": "NONE", "restartCount": None,
        })
        self.assertEqual(snapshot["origin"], {
            "reachable": False, "healthzStatus": None,
        })
        self.assertFalse(snapshot["recurring"]["reachable"])
        self.assertEqual(snapshot["recurring"]["status"], "UNREACHABLE")
        for key, value in snapshot["recurring"].items():
            if key not in {"reachable", "status"}:
                self.assertIsNone(value)

    def test_should_failClosed_when_containerAuthorityDoesNotMatch(self) -> None:
        payloads = {
            service: container_payload(
                self.project_name,
                service,
                self.compose_file,
            )
            for service in ("web", "api", "postgres")
        }
        payloads["api"]["Config"]["Labels"][
            "com.docker.compose.project.config_files"
        ] = "/tmp/different-compose.yaml"
        runner = FakeRunner(
            self.project_name,
            self.compose_file,
            service_payloads=payloads,
        )

        with self.assertRaises(production_status.ContractError):
            self.collect(runner)

    def test_should_distinguishMissingInvalidAndFutureBackupMarkers(self) -> None:
        bundle = self.create_valid_bundle()
        marker = self.backup_directory / "last-success.json"
        marker.unlink()
        missing = self.collect(FakeRunner(self.project_name, self.compose_file))
        self.assertEqual(missing["backup"]["markerState"], "MISSING")
        self.assertEqual(missing["backup"]["inventory"]["valid"], 1)
        self.assertIsNone(missing["backup"]["ageSeconds"])

        marker.write_text("{}\n", encoding="utf-8")
        marker.chmod(0o600)
        invalid = self.collect(FakeRunner(self.project_name, self.compose_file))
        self.assertEqual(invalid["backup"]["markerState"], "INVALID")
        self.assertIsNone(invalid["backup"]["createdAt"])

        metadata = backup_artifact.verify_bundle(bundle)
        future_marker = dict(metadata)
        future_marker["bundleDirectory"] = bundle.name
        future_marker["createdAt"] = "2026-08-29T03:17:00Z"
        marker.write_text(
            json.dumps(future_marker, ensure_ascii=True),
            encoding="utf-8",
        )
        marker.chmod(0o600)
        future = self.collect(FakeRunner(self.project_name, self.compose_file))
        self.assertEqual(future["backup"]["markerState"], "INVALID")
        self.assertIsNone(future["backup"]["ageSeconds"])

    def test_should_reportUnavailableFilesystem_when_statFails(self) -> None:
        snapshot = self.collect(
            FakeRunner(self.project_name, self.compose_file),
            statvfs=lambda _: (_ for _ in ()).throw(OSError("synthetic")),
        )

        self.assertEqual(snapshot["filesystem"], {
            "state": "UNAVAILABLE",
            "capacityBytes": None,
            "availableBytes": None,
            "usedPercent": None,
        })

    def test_should_parseDownHttpResponse_withoutLeakingFailureDetails(self) -> None:
        payload = recurring_health(status="DOWN")
        payload["components"]["recurringScheduler"]["details"][
            "lastPollSucceeded"
        ] = False

        parsed = production_status.parse_recurring_response(
            "503\n" + json.dumps(payload)
        )

        self.assertEqual(parsed["status"], "DOWN")
        self.assertFalse(parsed["lastPollSucceeded"])
        self.assertNotIn("recurringId", parsed)

    def collect(
        self,
        runner: FakeRunner,
        *,
        statvfs=None,
    ) -> dict:
        collector = production_status.ProductionStatusCollector(
            repo_root=self.repo_root,
            compose_file=self.compose_file,
            project_name=self.project_name,
            env_file=self.env_file,
            backup_directory=self.backup_directory,
            runner=runner,
            origin_fetch=lambda _: 200,
            statvfs=statvfs or synthetic_statvfs,
            now=lambda: NOW,
        )
        return collector.collect()

    def create_valid_bundle(self) -> Path:
        stem = backup_artifact.create_stem(CREATED_AT, "8")
        staging = self.backup_directory / f".our-ledger_backup_{stem}.partial"
        staging.mkdir(mode=0o700)
        dump = staging / f"{stem}.dump"
        dump.write_bytes(b"PGDMPsynthetic-status-archive")
        dump.chmod(0o600)
        backup_artifact.fsync_dump_file(
            self.backup_directory, staging, dump.name
        )
        backup_artifact.write_sidecars(
            self.backup_directory,
            staging,
            dump.name,
            CREATED_AT,
            "8",
            "pg_dump (PostgreSQL) 18.6",
            "18.6",
        )
        final_dump = backup_artifact.commit_bundle(
            self.backup_directory,
            staging,
            f"{stem}.backup",
        )
        return final_dump.parent

    def assert_commands_are_read_only(self, commands: list[list[str]]) -> None:
        self.assertTrue(commands)
        forbidden = {
            "up", "down", "start", "stop", "restart", "create", "rm",
            "remove", "kill", "pause", "unpause", "exec-psql",
        }
        for command in commands:
            self.assertTrue(forbidden.isdisjoint(command), command)
            self.assertNotIn("backup-production.sh", " ".join(command))
        compose_actions = [
            command[command.index("compose") + 1:]
            for command in commands
            if command[:2] == ["docker", "compose"]
        ]
        self.assertTrue(all(
            "config" in action or "ps" in action
            for action in compose_actions
        ))


def synthetic_statvfs(_: Path) -> os.statvfs_result:
    return os.statvfs_result((
        4096, 1000, 1000, 300, 400,
        0, 0, 0, 0, 255,
    ))


def directory_fingerprint(directory: Path) -> dict[str, tuple[str, int]]:
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(directory.rglob("*")):
        relative = str(path.relative_to(directory))
        if path.is_file():
            result[relative] = ("file", path.stat().st_size)
        else:
            result[relative] = ("directory", 0)
    return result


if __name__ == "__main__":
    unittest.main()
