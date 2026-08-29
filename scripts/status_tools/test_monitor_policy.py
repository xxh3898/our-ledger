from __future__ import annotations

import copy
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import unittest
from unittest import mock
import urllib.parse

from scripts.backup_tools import backup_artifact
from scripts.status_tools import monitor_policy
from scripts.status_tools import monitor_worker


OBSERVED = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.timezone.utc)


def instant(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def healthy_snapshot() -> dict:
    return {
        "formatVersion": 1,
        "observedAt": instant(OBSERVED),
        "services": {
            name: {"state": "RUNNING", "health": "HEALTHY", "restartCount": 0}
            for name in ("web", "api", "postgres")
        },
        "origin": {"reachable": True, "healthzStatus": 200},
        "recurring": {
            "reachable": True,
            "status": "UP",
            "enabled": True,
            "processStartedAt": instant(OBSERVED - dt.timedelta(hours=1)),
            "pollCountSinceStart": 10,
            "lastPollStartedAt": instant(OBSERVED - dt.timedelta(seconds=65)),
            "lastPollCompletedAt": instant(OBSERVED - dt.timedelta(seconds=60)),
            "lastPollSucceeded": True,
            "lastAdvancedOccurrenceCount": 0,
            "lastPollRuleFailureCount": 0,
            "totalRuleFailureCountSinceStart": 0,
            "consecutivePollExecutionFailures": 0,
            "lastPollExecutionFailureAt": None,
            "lastRuleFailureAt": None,
        },
        "backup": {
            "markerState": "VALID",
            "createdAt": instant(OBSERVED - dt.timedelta(hours=1)),
            "ageSeconds": 3600,
            "schemaVersion": "8",
            "sizeBytes": 123456,
            "inventory": {"valid": 3, "invalid": 0, "incomplete": 0, "foreign": 0},
        },
        "filesystem": {
            "state": "AVAILABLE",
            "capacityBytes": 1_000_000,
            "availableBytes": 500_000,
            "usedPercent": 50.0,
        },
    }


def advance(snapshot: dict, seconds: int) -> dict:
    result = copy.deepcopy(snapshot)
    current = monitor_policy.parse_instant(result["observedAt"], "observedAt")
    assert current is not None
    result["observedAt"] = instant(current + dt.timedelta(seconds=seconds))
    if result["backup"]["ageSeconds"] is not None:
        result["backup"]["ageSeconds"] += seconds
    return result


def signal_codes(result: dict) -> list[tuple[str, str | None, str]]:
    return [
        (signal["code"], signal.get("target"), signal["severity"])
        for signal in result["signals"]
    ]


class MonitorPolicyTest(unittest.TestCase):

    def test_should_return_ok_for_healthy_snapshot(self) -> None:
        result, state = monitor_policy.evaluate(healthy_snapshot())

        self.assertEqual(result, {
            "formatVersion": 1,
            "observedAt": "2026-08-29T12:00:00Z",
            "status": "OK",
            "signals": [],
        })
        self.assertEqual(state["lastOverallStatus"], "OK")
        self.assertEqual(state["serviceFailureStreaks"], {
            "web": 0, "api": 0, "postgres": 0, "recurring": 0,
        })

    def test_should_escalate_service_after_two_observations_and_reset_on_recovery(self) -> None:
        failed = healthy_snapshot()
        failed["services"]["web"]["health"] = "UNHEALTHY"

        first, first_state = monitor_policy.evaluate(failed)
        second, second_state = monitor_policy.evaluate(advance(failed, 60), first_state)

        self.assertIn(("SERVICE_PENDING", "web", "WARN"), signal_codes(first))
        self.assertIn(("SERVICE_DOWN", "web", "CRITICAL"), signal_codes(second))
        self.assertEqual(first_state["serviceFailureStreaks"]["web"], 1)
        self.assertEqual(second_state["serviceFailureStreaks"]["web"], 2)

        recovered, recovered_state = monitor_policy.evaluate(
            advance(healthy_snapshot(), 120), second_state
        )
        self.assertEqual(recovered["status"], "OK")
        self.assertEqual(recovered_state["serviceFailureStreaks"]["web"], 0)

    def test_should_keep_service_failure_streaks_independent(self) -> None:
        web_failed = healthy_snapshot()
        web_failed["services"]["web"]["state"] = "EXITED"
        _, state = monitor_policy.evaluate(web_failed)

        api_failed = advance(healthy_snapshot(), 60)
        api_failed["services"]["api"]["state"] = "MISSING"
        result, next_state = monitor_policy.evaluate(api_failed, state)

        self.assertIn(("SERVICE_PENDING", "api", "WARN"), signal_codes(result))
        self.assertNotIn(("SERVICE_DOWN", "api", "CRITICAL"), signal_codes(result))
        self.assertEqual(next_state["serviceFailureStreaks"]["web"], 0)
        self.assertEqual(next_state["serviceFailureStreaks"]["api"], 1)

    def test_should_escalate_origin_after_two_observations(self) -> None:
        failed = healthy_snapshot()
        failed["origin"] = {"reachable": True, "healthzStatus": 503}

        first, state = monitor_policy.evaluate(failed)
        second, _ = monitor_policy.evaluate(advance(failed, 60), state)

        self.assertIn(("ORIGIN_PENDING", None, "WARN"), signal_codes(first))
        self.assertIn(("ORIGIN_DOWN", None, "CRITICAL"), signal_codes(second))

    def test_should_escalate_recurring_reachability_independently(self) -> None:
        failed = healthy_snapshot()
        failed["recurring"] = {
            "reachable": False,
            "status": "UNREACHABLE",
            **{key: None for key in monitor_policy.RECURRING_DETAIL_KEYS},
        }

        first, state = monitor_policy.evaluate(failed)
        second, next_state = monitor_policy.evaluate(advance(failed, 60), state)

        self.assertIn(("SERVICE_PENDING", "recurring", "WARN"), signal_codes(first))
        self.assertIn(("SERVICE_DOWN", "recurring", "CRITICAL"), signal_codes(second))
        self.assertEqual(next_state["serviceFailureStreaks"]["web"], 0)

    def test_should_apply_recurring_startup_grace_exactly(self) -> None:
        starting = healthy_snapshot()
        starting["recurring"].update({
            "status": "UNKNOWN",
            "processStartedAt": instant(OBSERVED - dt.timedelta(seconds=299)),
            "pollCountSinceStart": 0,
            "lastPollStartedAt": None,
            "lastPollCompletedAt": None,
            "lastPollSucceeded": None,
            "lastAdvancedOccurrenceCount": 0,
            "lastPollRuleFailureCount": 0,
            "totalRuleFailureCountSinceStart": 0,
            "consecutivePollExecutionFailures": 0,
            "lastPollExecutionFailureAt": None,
            "lastRuleFailureAt": None,
        })
        result, _ = monitor_policy.evaluate(starting)
        self.assertIn(("RECURRING_STARTING", None, "WARN"), signal_codes(result))

        expired = copy.deepcopy(starting)
        expired["recurring"]["processStartedAt"] = instant(
            OBSERVED - dt.timedelta(seconds=300)
        )
        result, _ = monitor_policy.evaluate(expired)
        self.assertIn(("RECURRING_NOT_RUNNING", None, "CRITICAL"), signal_codes(result))

    def test_should_accept_first_poll_in_progress_without_counting_rule_failure(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["recurring"].update({
            "status": "UNKNOWN",
            "processStartedAt": instant(OBSERVED - dt.timedelta(seconds=120)),
            "pollCountSinceStart": 1,
            "lastPollStartedAt": instant(OBSERVED - dt.timedelta(seconds=5)),
            "lastPollCompletedAt": None,
            "lastPollSucceeded": None,
            "lastPollRuleFailureCount": 1,
            "totalRuleFailureCountSinceStart": 1,
            "lastRuleFailureAt": instant(OBSERVED - dt.timedelta(seconds=1)),
        })

        result, state = monitor_policy.evaluate(snapshot)

        self.assertIn(("RECURRING_STARTING", None, "WARN"), signal_codes(result))
        self.assertNotIn(
            ("RECURRING_RULE_FAILURE", None, "WARN"), signal_codes(result)
        )
        self.assertEqual(state["recurringRuleFailureStreak"], 0)
        self.assertIsNone(state["lastRecurringPollCompletedAtSeen"])

        expired = copy.deepcopy(snapshot)
        expired["recurring"]["processStartedAt"] = instant(
            OBSERVED - dt.timedelta(seconds=300)
        )
        result, _ = monitor_policy.evaluate(expired)
        self.assertIn(("RECURRING_NOT_RUNNING", None, "CRITICAL"), signal_codes(result))

    def test_should_require_recurring_enabled_in_production(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["recurring"]["enabled"] = False

        result, _ = monitor_policy.evaluate(snapshot)

        self.assertIn(("RECURRING_NOT_RUNNING", None, "CRITICAL"), signal_codes(result))

    def test_should_mark_poll_stale_only_after_five_minutes(self) -> None:
        exact = healthy_snapshot()
        exact["recurring"]["lastPollCompletedAt"] = instant(
            OBSERVED - dt.timedelta(seconds=300)
        )
        result, _ = monitor_policy.evaluate(exact)
        self.assertNotIn(("RECURRING_STALE", None, "CRITICAL"), signal_codes(result))

        stale = healthy_snapshot()
        stale["recurring"]["lastPollCompletedAt"] = instant(
            OBSERVED - dt.timedelta(seconds=301)
        )
        result, _ = monitor_policy.evaluate(stale)
        self.assertIn(("RECURRING_STALE", None, "CRITICAL"), signal_codes(result))

    def test_should_make_top_level_recurring_failure_immediately_critical(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["recurring"].update({
            "status": "DOWN",
            "lastPollSucceeded": False,
            "consecutivePollExecutionFailures": 1,
            "lastPollExecutionFailureAt": snapshot["recurring"]["lastPollCompletedAt"],
        })

        result, _ = monitor_policy.evaluate(snapshot)

        self.assertIn(
            ("RECURRING_EXECUTION_FAILED", None, "CRITICAL"), signal_codes(result)
        )

    def test_should_increment_rule_failure_once_per_new_poll(self) -> None:
        first_poll = healthy_snapshot()
        first_poll["recurring"].update({
            "lastPollRuleFailureCount": 1,
            "totalRuleFailureCountSinceStart": 1,
            "lastRuleFailureAt": first_poll["recurring"]["lastPollCompletedAt"],
        })
        first, state = monitor_policy.evaluate(first_poll)
        self.assertIn(("RECURRING_RULE_FAILURE", None, "WARN"), signal_codes(first))
        self.assertEqual(state["recurringRuleFailureStreak"], 1)

        repeated = advance(first_poll, 60)
        second, repeated_state = monitor_policy.evaluate(repeated, state)
        self.assertIn(("RECURRING_RULE_FAILURE", None, "WARN"), signal_codes(second))
        self.assertEqual(repeated_state["recurringRuleFailureStreak"], 1)

        next_poll = advance(first_poll, 120)
        next_poll["recurring"]["lastPollStartedAt"] = instant(
            OBSERVED + dt.timedelta(seconds=55)
        )
        next_poll["recurring"]["lastPollCompletedAt"] = instant(
            OBSERVED + dt.timedelta(seconds=60)
        )
        next_poll["recurring"]["lastRuleFailureAt"] = next_poll["recurring"]["lastPollCompletedAt"]
        third, next_state = monitor_policy.evaluate(next_poll, repeated_state)
        self.assertEqual(next_state["recurringRuleFailureStreak"], 2)
        self.assertIn(("RECURRING_RULE_FAILURE", None, "WARN"), signal_codes(third))

        third_poll = advance(next_poll, 60)
        third_poll["recurring"]["lastPollStartedAt"] = instant(
            OBSERVED + dt.timedelta(seconds=115)
        )
        third_poll["recurring"]["lastPollCompletedAt"] = instant(
            OBSERVED + dt.timedelta(seconds=120)
        )
        third_poll["recurring"]["lastRuleFailureAt"] = third_poll["recurring"]["lastPollCompletedAt"]
        fourth, final_state = monitor_policy.evaluate(third_poll, next_state)
        self.assertEqual(final_state["recurringRuleFailureStreak"], 3)
        self.assertIn(
            ("RECURRING_RULE_FAILURE", None, "CRITICAL"), signal_codes(fourth)
        )

    def test_should_reset_rule_failure_on_new_clean_poll(self) -> None:
        failed = healthy_snapshot()
        failed["recurring"]["lastPollRuleFailureCount"] = 1
        _, state = monitor_policy.evaluate(failed)

        clean = advance(healthy_snapshot(), 60)
        clean["recurring"]["lastPollStartedAt"] = instant(OBSERVED - dt.timedelta(seconds=5))
        clean["recurring"]["lastPollCompletedAt"] = instant(OBSERVED)
        result, next_state = monitor_policy.evaluate(clean, state)

        self.assertEqual(next_state["recurringRuleFailureStreak"], 0)
        self.assertNotIn(
            ("RECURRING_RULE_FAILURE", None, "WARN"), signal_codes(result)
        )

    def test_should_apply_backup_freshness_exactly(self) -> None:
        exact = healthy_snapshot()
        exact["backup"]["ageSeconds"] = 7 * 60 * 60
        result, _ = monitor_policy.evaluate(exact)
        self.assertIn(("BACKUP_STALE", None, "CRITICAL"), signal_codes(result))

        fresh = healthy_snapshot()
        fresh["backup"]["ageSeconds"] = 7 * 60 * 60 - 1
        result, _ = monitor_policy.evaluate(fresh)
        self.assertNotIn(("BACKUP_STALE", None, "CRITICAL"), signal_codes(result))

    def test_should_fail_closed_for_each_backup_marker_state(self) -> None:
        expected = {
            "MISSING": "BACKUP_MISSING",
            "INVALID": "BACKUP_INVALID",
            "UNAVAILABLE": "BACKUP_UNAVAILABLE",
        }
        for marker_state, code in expected.items():
            with self.subTest(marker_state=marker_state):
                snapshot = healthy_snapshot()
                snapshot["backup"].update({
                    "markerState": marker_state,
                    "createdAt": None,
                    "ageSeconds": None,
                    "schemaVersion": None,
                    "sizeBytes": None,
                })
                if marker_state == "UNAVAILABLE":
                    snapshot["backup"]["inventory"] = {
                        "valid": None, "invalid": None, "incomplete": None, "foreign": None,
                    }
                result, _ = monitor_policy.evaluate(snapshot)
                self.assertIn((code, None, "CRITICAL"), signal_codes(result))

    def test_should_warn_for_invalid_or_incomplete_inventory_but_not_foreign(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["backup"]["inventory"].update({"invalid": 1, "incomplete": 1})
        result, _ = monitor_policy.evaluate(snapshot)
        self.assertIn(
            ("BACKUP_INVENTORY_WARNING", None, "WARN"), signal_codes(result)
        )

        foreign_only = healthy_snapshot()
        foreign_only["backup"]["inventory"]["foreign"] = 9
        result, _ = monitor_policy.evaluate(foreign_only)
        self.assertEqual(result["status"], "OK")

    def test_should_apply_disk_boundaries_exactly(self) -> None:
        cases = (
            (79.9, None, "OK"),
            (80.0, "DISK_USAGE_WARNING", "WARN"),
            (89.9, "DISK_USAGE_WARNING", "WARN"),
            (90.0, "DISK_USAGE_CRITICAL", "CRITICAL"),
        )
        for used_percent, code, status in cases:
            with self.subTest(used_percent=used_percent):
                snapshot = healthy_snapshot()
                snapshot["filesystem"]["usedPercent"] = used_percent
                result, _ = monitor_policy.evaluate(snapshot)
                self.assertEqual(result["status"], status)
                if code is not None:
                    self.assertTrue(any(signal["code"] == code for signal in result["signals"]))

    def test_should_fail_closed_when_filesystem_is_unavailable(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["filesystem"] = {
            "state": "UNAVAILABLE",
            "capacityBytes": None,
            "availableBytes": None,
            "usedPercent": None,
        }

        result, _ = monitor_policy.evaluate(snapshot)

        self.assertIn(
            ("FILESYSTEM_UNAVAILABLE", None, "CRITICAL"), signal_codes(result)
        )

    def test_should_reject_snapshot_extra_fields_instead_of_echoing_them(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["secret"] = "never-output-this"

        with self.assertRaises(monitor_policy.ContractError):
            monitor_policy.evaluate(snapshot)

    def test_should_return_only_policy_and_non_sensitive_state_allowlists(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["services"]["web"]["state"] = "EXITED"
        result, state = monitor_policy.evaluate(snapshot)

        self.assertEqual(set(result), {"formatVersion", "observedAt", "status", "signals"})
        self.assertEqual(set(state), monitor_policy.STATE_KEYS)
        self.assertTrue(all(set(signal) <= {"code", "severity", "target"} for signal in result["signals"]))
        self.assertTrue(all(signal["code"] in monitor_policy.SIGNAL_CODES for signal in result["signals"]))
        encoded = json.dumps({"result": result, "state": state})
        for forbidden in ("containerId", "bundleDirectory", "sha256", "email", "memo", "amount"):
            self.assertNotIn(forbidden, encoded)

    def test_should_not_treat_missing_state_as_success_for_first_failure(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["services"]["postgres"]["state"] = "MISSING"

        result, state = monitor_policy.evaluate(snapshot, None)

        self.assertEqual(result["status"], "WARN")
        self.assertEqual(state["serviceFailureStreaks"]["postgres"], 1)

    def test_should_reject_corrupt_state_and_non_monotonic_observation(self) -> None:
        corrupt = monitor_policy.default_state()
        corrupt["serviceFailureStreaks"]["web"] = -1
        with self.assertRaises(monitor_policy.ContractError):
            monitor_policy.evaluate(healthy_snapshot(), corrupt)

        _, state = monitor_policy.evaluate(healthy_snapshot())
        with self.assertRaises(monitor_policy.ContractError):
            monitor_policy.evaluate(healthy_snapshot(), state)

    def test_should_build_fail_closed_result_without_raw_detail(self) -> None:
        result = monitor_policy.failure_result(
            "2026-08-29T12:00:00Z", "STATE_INVALID"
        )

        self.assertEqual(result, {
            "formatVersion": 1,
            "observedAt": "2026-08-29T12:00:00Z",
            "status": "CRITICAL",
            "signals": [{"code": "STATE_INVALID", "severity": "CRITICAL"}],
        })


class MonitorStateAndWorkerTest(unittest.TestCase):

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="our-ledger-monitor-test.")
        self.root = Path(self.temporary.name)
        self.repo_root = self.root / "repo"
        self.repo_root.mkdir(mode=0o700)
        self.state_directory = self.root / "state"
        self.state_directory.mkdir(mode=0o700)
        self.backup_directory = self.root / "backups"
        self.backup_directory.mkdir(mode=0o700)
        self.config_path = self.root / "monitor-heartbeat.conf"
        self.config_path.write_text(
            "STATUS_HEARTBEAT_URL=https://monitor.invalid/api/push/test-token\n",
            encoding="utf-8",
        )
        self.config_path.chmod(0o600)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_valid_backup(
        self, backup_directory: Path
    ) -> Path:
        backup_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        created_at = "2026-08-29T03:15:00Z"
        stem = backup_artifact.create_stem(created_at, "8")
        staging = backup_directory / f".our-ledger_backup_{stem}.partial"
        staging.mkdir(mode=0o700)
        dump = staging / f"{stem}.dump"
        dump.write_bytes(b"PGDMPsynthetic-custom-archive")
        dump.chmod(0o600)
        backup_artifact.fsync_dump_file(backup_directory, staging, dump.name)
        backup_artifact.write_sidecars(
            backup_directory,
            staging,
            dump.name,
            created_at,
            "8",
            "pg_dump (PostgreSQL) 18.6",
            "18.6",
        )
        final_dump = backup_artifact.commit_bundle(
            backup_directory, staging, f"{stem}.backup"
        )
        bundle = final_dump.parent
        backup_artifact.verify_bundle(bundle)
        return bundle

    def tree_fingerprint(self, root: Path) -> dict[str, tuple]:
        result: dict[str, tuple] = {}
        for path in sorted(root.rglob("*")):
            relative = str(path.relative_to(root))
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if path.is_symlink():
                result[relative] = ("symlink", mode, os.readlink(path))
            elif path.is_file():
                result[relative] = (
                    "file",
                    mode,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            else:
                result[relative] = ("directory", mode)
        return result

    def test_should_atomically_store_owner_only_minimal_state(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        state = monitor_policy.default_state()
        state.update({
            "lastObservedAt": "2026-08-29T12:00:00Z",
            "lastOverallStatus": "WARN",
        })
        state["serviceFailureStreaks"]["web"] = 1

        store.save(state)

        self.assertEqual(store.load(), state)
        self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
        self.assertEqual(
            [item.name for item in self.state_directory.iterdir() if item.name.startswith(".monitor-state.")],
            [],
        )

    def test_should_fsync_state_file_before_atomic_replace_and_directory(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        state = monitor_policy.default_state()
        state["lastObservedAt"] = "2026-08-29T12:00:00Z"
        events: list[str] = []
        real_fsync = os.fsync
        real_replace = os.replace

        def tracked_fsync(descriptor: int) -> None:
            kind = "directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file"
            events.append(f"fsync-{kind}")
            real_fsync(descriptor)

        def tracked_replace(source: os.PathLike, destination: os.PathLike) -> None:
            events.append("replace")
            real_replace(source, destination)

        with mock.patch.object(monitor_worker.os, "fsync", side_effect=tracked_fsync), mock.patch.object(
            monitor_worker.os, "replace", side_effect=tracked_replace
        ):
            store.save(state)

        self.assertLess(events.index("fsync-file"), events.index("replace"))
        self.assertLess(events.index("replace"), events.index("fsync-directory"))

    def test_should_preserve_previous_state_when_atomic_replace_fails(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        previous = monitor_policy.default_state()
        previous["lastObservedAt"] = "2026-08-29T11:59:00Z"
        store.save(previous)
        before = store.path.read_bytes()
        updated = copy.deepcopy(previous)
        updated["lastObservedAt"] = "2026-08-29T12:00:00Z"

        with mock.patch.object(
            monitor_worker.os,
            "replace",
            side_effect=OSError("synthetic replace failure"),
        ):
            with self.assertRaises(OSError):
                store.save(updated)

        self.assertEqual(store.path.read_bytes(), before)
        self.assertEqual(
            [item.name for item in self.state_directory.iterdir() if item.name.startswith(".monitor-state.")],
            [],
        )

    def test_should_reject_corrupt_symlink_or_permissive_state_without_reset(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        corrupt = b'{"formatVersion":'
        store.path.write_bytes(corrupt)
        store.path.chmod(0o600)
        with self.assertRaises(monitor_worker.ContractError):
            store.load()
        self.assertEqual(store.path.read_bytes(), corrupt)

        store.path.chmod(0o644)
        with self.assertRaises(monitor_worker.ContractError):
            store.load()
        store.path.unlink()

        target = self.root / "outside-state.json"
        target.write_text("{}\n", encoding="utf-8")
        target.chmod(0o600)
        store.path.symlink_to(target)
        with self.assertRaises(monitor_worker.ContractError):
            store.load()

    def test_should_require_external_canonical_owner_only_paths(self) -> None:
        validated = monitor_worker.validate_state_directory(
            self.repo_root, str(self.state_directory)
        )
        self.assertEqual(validated, self.state_directory.resolve())

        inside = self.repo_root / "state"
        inside.mkdir(mode=0o700)
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.validate_state_directory(self.repo_root, str(inside))

        nested = self.root / "nested"
        nested.mkdir(mode=0o700)
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.validate_state_directory(
                self.repo_root, str(nested / ".." / "state")
            )

        self.state_directory.chmod(0o755)
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.validate_state_directory(
                self.repo_root, str(self.state_directory)
            )

    def test_should_reject_backup_state_path_overlap_without_mutation(self) -> None:
        cases: list[tuple[str, Path, Path]] = []

        equal_backup = self.root / "equal-backup"
        self.create_valid_backup(equal_backup)
        cases.append(("equal", equal_backup, equal_backup))

        bundle_backup = self.root / "bundle-backup"
        bundle = self.create_valid_backup(bundle_backup)
        cases.append(("verified-bundle", bundle_backup, bundle))

        ancestor_state = self.root / "ancestor-state"
        ancestor_state.mkdir(mode=0o700)
        nested_backup = ancestor_state / "backups"
        self.create_valid_backup(nested_backup)
        cases.append(("state-ancestor", nested_backup, ancestor_state))

        descendant_backup = self.root / "descendant-backup"
        self.create_valid_backup(descendant_backup)
        nested_state = descendant_backup / "monitor-state"
        nested_state.mkdir(mode=0o700)
        cases.append(("state-descendant", descendant_backup, nested_state))

        for label, backup_directory, state_directory in cases:
            with self.subTest(label=label):
                before = self.tree_fingerprint(backup_directory)
                provider = mock.Mock(return_value=healthy_snapshot())
                sender = mock.Mock()

                with self.assertRaises(monitor_worker.ContractError):
                    monitor_worker.run_monitor(
                        repo_root=self.repo_root,
                        project_name="our-ledger",
                        env_file="/synthetic/env",
                        backup_directory=str(backup_directory),
                        state_directory_value=str(state_directory),
                        heartbeat_config_value=str(self.config_path),
                        snapshot_provider=provider,
                        heartbeat_sender=sender,
                    )

                provider.assert_not_called()
                sender.assert_not_called()
                self.assertEqual(self.tree_fingerprint(backup_directory), before)
                self.assertFalse(
                    os.path.lexists(state_directory / monitor_worker.LOCK_FILENAME)
                )
                self.assertFalse(
                    os.path.lexists(state_directory / monitor_worker.STATE_FILENAME)
                )
                self.assertEqual(
                    list(state_directory.glob(".monitor-state.*")), []
                )

    def test_should_reject_unexpected_state_entry_before_lock(self) -> None:
        unexpected = self.state_directory / "unexpected.txt"
        unexpected.write_bytes(b"preserve\n")
        unexpected.chmod(0o600)
        provider = mock.Mock(return_value=healthy_snapshot())
        sender = mock.Mock()

        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.run_monitor(
                repo_root=self.repo_root,
                project_name="our-ledger",
                env_file="/synthetic/env",
                backup_directory=str(self.backup_directory),
                state_directory_value=str(self.state_directory),
                heartbeat_config_value=str(self.config_path),
                snapshot_provider=provider,
                heartbeat_sender=sender,
            )

        provider.assert_not_called()
        sender.assert_not_called()
        self.assertEqual(unexpected.read_bytes(), b"preserve\n")
        self.assertFalse(
            os.path.lexists(self.state_directory / monitor_worker.LOCK_FILENAME)
        )
        self.assertFalse(
            os.path.lexists(self.state_directory / monitor_worker.STATE_FILENAME)
        )

    def test_should_use_non_blocking_kernel_lock(self) -> None:
        with monitor_worker.MonitorLock(self.state_directory):
            with self.assertRaises(monitor_worker.LockBusyError):
                with monitor_worker.MonitorLock(self.state_directory):
                    self.fail("second monitor lock unexpectedly succeeded")

        lock_path = self.state_directory / monitor_worker.LOCK_FILENAME
        self.assertTrue(lock_path.is_file())
        self.assertEqual(stat.S_IMODE(lock_path.stat().st_mode), 0o600)

    def test_should_load_only_exact_owner_only_heartbeat_config(self) -> None:
        validated = monitor_worker.validate_heartbeat_config(
            self.repo_root, str(self.config_path)
        )
        url = monitor_worker.load_heartbeat_url(validated)
        self.assertTrue(url.startswith("https://"))

        self.config_path.write_text(
            "STATUS_HEARTBEAT_URL=https://monitor.invalid/api/push/one\n"
            "EXTRA=value\n",
            encoding="utf-8",
        )
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.load_heartbeat_url(validated)

        self.config_path.write_text(
            "STATUS_HEARTBEAT_URL=https://monitor.invalid/api/push/one\n",
            encoding="utf-8",
        )
        self.config_path.chmod(0o644)
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.validate_heartbeat_config(
                self.repo_root, str(self.config_path)
            )

        self.config_path.chmod(0o600)
        config_target = self.root / "config-target"
        config_target.write_text(
            "STATUS_HEARTBEAT_URL=https://monitor.invalid/api/push/target\n",
            encoding="utf-8",
        )
        config_target.chmod(0o600)
        config_link = self.root / "config-link"
        config_link.symlink_to(config_target)
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.validate_heartbeat_config(
                self.repo_root, str(config_link)
            )

    def test_should_accept_https_or_loopback_http_push_url_only(self) -> None:
        accepted = (
            "https://monitor.example/api/push/token-1",
            "http://127.0.0.1:3001/api/push/token_2?status=up&msg=OK&ping=",
            "http://localhost:3001/api/push/token",
        )
        for value in accepted:
            self.assertEqual(monitor_worker.validate_heartbeat_url(value), value)

        rejected = (
            "http://monitor.example/api/push/token",
            "https://user:password@monitor.example/api/push/token",
            "https://monitor.example/not-push/token",
            "https://monitor.example/api/push/token#fragment",
            "file:///api/push/token",
        )
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(monitor_worker.ContractError):
                    monitor_worker.validate_heartbeat_url(value)

    def test_should_update_state_before_delivery(self) -> None:
        deliveries: list[dict] = []

        def provider(_repo: Path, _project: str, _env: str, _backup: str) -> dict:
            return healthy_snapshot()

        def sender(_url: str, result: dict) -> None:
            stored = monitor_worker.MonitorStateStore(self.state_directory).load()
            self.assertEqual(stored["lastObservedAt"], result["observedAt"])
            deliveries.append(result)

        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            heartbeat_config_value=str(self.config_path),
            snapshot_provider=provider,
            heartbeat_sender=sender,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(deliveries, [result])

    def test_should_preserve_state_when_status_is_unavailable(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        previous = monitor_policy.default_state()
        previous["lastObservedAt"] = "2026-08-29T11:59:00Z"
        store.save(previous)
        before = store.path.read_bytes()
        delivered: list[dict] = []

        def unavailable(_repo: Path, _project: str, _env: str, _backup: str) -> dict:
            raise monitor_worker.StatusUnavailableError("synthetic")

        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            heartbeat_config_value=str(self.config_path),
            snapshot_provider=unavailable,
            heartbeat_sender=lambda _url, value: delivered.append(value),
            now=lambda: OBSERVED,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["signals"][0]["code"], "STATUS_UNAVAILABLE")
        self.assertEqual(delivered, [result])
        self.assertEqual(store.path.read_bytes(), before)

    def test_should_report_corrupt_state_as_critical_without_overwrite(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        corrupt = b"not-json\n"
        store.path.write_bytes(corrupt)
        store.path.chmod(0o600)
        delivered: list[dict] = []

        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            heartbeat_config_value=str(self.config_path),
            snapshot_provider=lambda *_args: healthy_snapshot(),
            heartbeat_sender=lambda _url, value: delivered.append(value),
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["signals"][0]["code"], "STATE_INVALID")
        self.assertEqual(delivered, [result])
        self.assertEqual(store.path.read_bytes(), corrupt)

    def test_should_keep_state_when_delivery_fails_after_update(self) -> None:
        def failed_delivery(_url: str, _result: dict) -> None:
            self.assertTrue(
                (self.state_directory / monitor_worker.STATE_FILENAME).is_file()
            )
            raise monitor_worker.DeliveryError("synthetic")

        with self.assertRaises(monitor_worker.DeliveryError):
            monitor_worker.run_monitor(
                repo_root=self.repo_root,
                project_name="our-ledger",
                env_file="/synthetic/env",
                backup_directory=str(self.backup_directory),
                state_directory_value=str(self.state_directory),
                heartbeat_config_value=str(self.config_path),
                snapshot_provider=lambda *_args: healthy_snapshot(),
                heartbeat_sender=failed_delivery,
            )
        stored = monitor_worker.MonitorStateStore(self.state_directory).load()
        self.assertEqual(stored["lastObservedAt"], "2026-08-29T12:00:00Z")


class KumaHandler(BaseHTTPRequestHandler):
    response_code = 200
    response_body = b"ok"
    redirect_location: str | None = None
    requests: list[str] = []

    def do_GET(self) -> None:
        type(self).requests.append(self.path)
        self.send_response(type(self).response_code)
        if type(self).redirect_location is not None:
            self.send_header("Location", type(self).redirect_location)
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


class KumaAdapterTest(unittest.TestCase):

    def setUp(self) -> None:
        KumaHandler.response_code = 200
        KumaHandler.response_body = b"ok"
        KumaHandler.redirect_location = None
        KumaHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), KumaHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = (
            f"http://127.0.0.1:{self.server.server_port}/api/push/test-token"
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_should_map_ok_warn_and_critical_to_up_up_down(self) -> None:
        ok, _ = monitor_policy.evaluate(healthy_snapshot())
        warning_snapshot = healthy_snapshot()
        warning_snapshot["services"]["web"]["state"] = "EXITED"
        warning, _ = monitor_policy.evaluate(warning_snapshot)
        critical = monitor_policy.failure_result(
            "2026-08-29T12:00:00Z", "STATUS_UNAVAILABLE"
        )

        for result in (ok, warning, critical):
            monitor_worker.send_heartbeat(self.base_url, result)

        queries = [
            urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            for path in KumaHandler.requests
        ]
        self.assertEqual([query["status"][0] for query in queries], ["up", "up", "down"])
        self.assertEqual(queries[0]["msg"][0], "OK")
        self.assertIn("SERVICE_PENDING:web", queries[1]["msg"][0])
        self.assertIn("STATUS_UNAVAILABLE", queries[2]["msg"][0])

    def test_should_reject_redirect_without_following_secret_url(self) -> None:
        KumaHandler.response_code = 302
        KumaHandler.redirect_location = f"http://127.0.0.1:{self.server.server_port}/redirect-target"
        result, _ = monitor_policy.evaluate(healthy_snapshot())

        with self.assertRaises(monitor_worker.DeliveryError) as raised:
            monitor_worker.send_heartbeat(self.base_url, result)

        self.assertEqual(len(KumaHandler.requests), 1)
        self.assertNotIn("test-token", str(raised.exception))

    def test_should_reject_oversized_response(self) -> None:
        KumaHandler.response_body = b"x" * (monitor_worker.MAX_RESPONSE_BYTES + 1)
        result, _ = monitor_policy.evaluate(healthy_snapshot())

        with self.assertRaises(monitor_worker.DeliveryError):
            monitor_worker.send_heartbeat(self.base_url, result)

    def test_should_apply_bounded_timeout_and_hide_secret_on_timeout(self) -> None:
        result, _ = monitor_policy.evaluate(healthy_snapshot())
        secret_url = self.base_url.replace("test-token", "private-token")
        opener = mock.Mock()
        opener.open.side_effect = TimeoutError("synthetic timeout")

        with mock.patch.object(
            monitor_worker.urllib.request,
            "build_opener",
            return_value=opener,
        ):
            with self.assertRaises(monitor_worker.DeliveryError) as raised:
                monitor_worker.send_heartbeat(secret_url, result)

        opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 5)
        self.assertNotIn("private-token", str(raised.exception))

    def test_should_report_network_failure_without_secret_url(self) -> None:
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        result, _ = monitor_policy.evaluate(healthy_snapshot())
        secret_url = f"http://127.0.0.1:{port}/api/push/private-token"

        with self.assertRaises(monitor_worker.DeliveryError) as raised:
            monitor_worker.send_heartbeat(secret_url, result)

        self.assertNotIn("private-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
