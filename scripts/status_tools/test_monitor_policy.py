from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

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

        legacy = monitor_policy.default_state()
        legacy["formatVersion"] = 1
        with self.assertRaises(monitor_policy.ContractError):
            monitor_policy.validate_state(legacy)

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
        self.reporter_path = self.root / monitor_worker.HOMEOPS_REPORTER_FILENAME
        self.reporter_path.write_text(
            "#!/usr/bin/python3\n"
            "import sys\n"
            "raise SystemExit(0 if sys.argv == [sys.argv[0], 'signal'] else 2)\n",
            encoding="utf-8",
        )
        self.reporter_path.chmod(0o700)

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
                        homeops_reporter_value=str(self.reporter_path),
                        snapshot_provider=provider,
                        homeops_sender=sender,
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
                homeops_reporter_value=str(self.reporter_path),
                snapshot_provider=provider,
                homeops_sender=sender,
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

    def test_should_validate_external_executable_homeops_reporter(self) -> None:
        authority = monitor_worker.validate_homeops_reporter(
            self.repo_root, str(self.reporter_path)
        )
        self.assertEqual(authority.path, self.reporter_path.resolve())

        invalid_cases: list[tuple[str, Path]] = []
        wrong_name = self.root / "reporter.py"
        wrong_name.write_text("#!/bin/sh\n", encoding="utf-8")
        wrong_name.chmod(0o700)
        invalid_cases.append(("identity", wrong_name))

        inside = self.repo_root / monitor_worker.HOMEOPS_REPORTER_FILENAME
        inside.write_text("#!/bin/sh\n", encoding="utf-8")
        inside.chmod(0o700)
        invalid_cases.append(("repository", inside))

        permissive = self.root / "permissive" / monitor_worker.HOMEOPS_REPORTER_FILENAME
        permissive.parent.mkdir(mode=0o700)
        permissive.write_text("#!/bin/sh\n", encoding="utf-8")
        permissive.chmod(0o720)
        invalid_cases.append(("group-write", permissive))

        not_executable = self.root / "not-executable" / monitor_worker.HOMEOPS_REPORTER_FILENAME
        not_executable.parent.mkdir(mode=0o700)
        not_executable.write_text("#!/bin/sh\n", encoding="utf-8")
        not_executable.chmod(0o600)
        invalid_cases.append(("not-executable", not_executable))

        symlink = self.root / "symlink" / monitor_worker.HOMEOPS_REPORTER_FILENAME
        symlink.parent.mkdir(mode=0o700)
        symlink.symlink_to(self.reporter_path)
        invalid_cases.append(("leaf-symlink", symlink))

        directory = self.root / "directory" / monitor_worker.HOMEOPS_REPORTER_FILENAME
        directory.mkdir(mode=0o700, parents=True)
        invalid_cases.append(("not-regular", directory))

        for label, path in invalid_cases:
            with self.subTest(label=label):
                with self.assertRaises(monitor_worker.ContractError):
                    monitor_worker.validate_homeops_reporter(
                        self.repo_root, str(path)
                    )

        provider = mock.Mock(return_value=healthy_snapshot())
        sender = mock.Mock()
        with self.assertRaises(monitor_worker.ContractError):
            monitor_worker.run_monitor(
                repo_root=self.repo_root,
                project_name="our-ledger",
                env_file="/synthetic/env",
                backup_directory=str(self.backup_directory),
                state_directory_value=str(self.state_directory),
                homeops_reporter_value=str(permissive),
                snapshot_provider=provider,
                homeops_sender=sender,
            )
        provider.assert_not_called()
        sender.assert_not_called()
        self.assertFalse(os.path.lexists(self.state_directory / monitor_worker.LOCK_FILENAME))
        self.assertFalse(os.path.lexists(self.state_directory / monitor_worker.STATE_FILENAME))

    def test_should_not_call_reporter_without_supported_disk_transition(self) -> None:
        sender = mock.Mock()
        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: healthy_snapshot(),
            homeops_sender=sender,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "OK")
        sender.assert_not_called()

    def test_should_preserve_state_when_status_is_unavailable(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        previous = monitor_policy.default_state()
        previous["lastObservedAt"] = "2026-08-29T11:59:00Z"
        store.save(previous)
        before = store.path.read_bytes()
        sender = mock.Mock()

        def unavailable(_repo: Path, _project: str, _env: str, _backup: str) -> dict:
            raise monitor_worker.StatusUnavailableError("synthetic")

        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=unavailable,
            homeops_sender=sender,
            now=lambda: OBSERVED,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["signals"][0]["code"], "STATUS_UNAVAILABLE")
        sender.assert_not_called()
        self.assertEqual(store.path.read_bytes(), before)

    def test_should_report_corrupt_state_as_critical_without_overwrite(self) -> None:
        store = monitor_worker.MonitorStateStore(self.state_directory)
        corrupt = b"not-json\n"
        store.path.write_bytes(corrupt)
        store.path.chmod(0o600)
        provider = mock.Mock(return_value=healthy_snapshot())
        sender = mock.Mock()

        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=provider,
            homeops_sender=sender,
            now=lambda: OBSERVED,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["signals"][0]["code"], "STATE_INVALID")
        provider.assert_not_called()
        sender.assert_not_called()
        self.assertEqual(store.path.read_bytes(), corrupt)

    def test_should_reject_legacy_state_without_reset_or_external_calls(self) -> None:
        legacy = monitor_policy.default_state()
        legacy["formatVersion"] = 1
        content = (json.dumps(legacy, sort_keys=True) + "\n").encode("utf-8")
        state_path = self.state_directory / monitor_worker.STATE_FILENAME
        state_path.write_bytes(content)
        state_path.chmod(0o600)
        provider = mock.Mock(return_value=healthy_snapshot())
        sender = mock.Mock()

        result, exit_code = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=provider,
            homeops_sender=sender,
            now=lambda: OBSERVED,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["signals"][0]["code"], "STATE_INVALID")
        provider.assert_not_called()
        sender.assert_not_called()
        self.assertEqual(state_path.read_bytes(), content)


    def test_should_deliver_disk_alert_and_recovery_once_per_episode(self) -> None:
        deliveries: list[dict] = []

        def sender(_reporter: monitor_worker.HomeOpsReporter, payload: dict) -> None:
            stored = monitor_worker.MonitorStateStore(self.state_directory).load()
            self.assertEqual(stored["homeOpsDisk"]["pendingSignal"], payload)
            deliveries.append(copy.deepcopy(payload))

        def run(snapshot: dict) -> tuple[dict, int]:
            return monitor_worker.run_monitor(
                repo_root=self.repo_root,
                project_name="our-ledger",
                env_file="/synthetic/env",
                backup_directory=str(self.backup_directory),
                state_directory_value=str(self.state_directory),
                homeops_reporter_value=str(self.reporter_path),
                snapshot_provider=lambda *_args: snapshot,
                homeops_sender=sender,
            )

        below = healthy_snapshot()
        below["filesystem"]["usedPercent"] = 79.9
        run(below)
        self.assertEqual(deliveries, [])

        entered = advance(healthy_snapshot(), 60)
        entered["filesystem"]["usedPercent"] = 80.0
        warning, exit_code = run(entered)
        self.assertEqual((warning["status"], exit_code), ("WARN", 0))
        self.assertEqual(deliveries[0], {
            "eventKey": "our-ledger:disk-low:1:alert",
            "episodeKey": "our-ledger:disk-low:1",
            "project": "our-ledger",
            "signalType": "DISK_LOW",
            "status": "ALERT",
            "observedAt": "2026-08-29T12:01:00Z",
            "availablePercent": 20.0,
            "thresholdPercent": 20,
        })

        for seconds, used_percent in ((120, 85.0), (180, 90.0)):
            active = advance(healthy_snapshot(), seconds)
            active["filesystem"]["usedPercent"] = used_percent
            run(active)
        self.assertEqual(len(deliveries), 1)

        recovered = advance(healthy_snapshot(), 240)
        recovered["filesystem"]["usedPercent"] = 79.9
        run(recovered)
        self.assertEqual(deliveries[1]["status"], "RECOVERED")
        self.assertEqual(deliveries[1]["episodeKey"], deliveries[0]["episodeKey"])
        self.assertEqual(deliveries[1]["availablePercent"], 20.1)

        reentered = advance(healthy_snapshot(), 300)
        reentered["filesystem"]["usedPercent"] = 80.0
        run(reentered)
        self.assertEqual(deliveries[2]["status"], "ALERT")
        self.assertEqual(deliveries[2]["episodeKey"], "our-ledger:disk-low:2")
        state = monitor_worker.MonitorStateStore(self.state_directory).load()
        self.assertEqual(state["homeOpsDisk"], {
            "episodeSequence": 2,
            "activeEpisodeKey": "our-ledger:disk-low:2",
            "pendingSignal": None,
        })

    def test_should_not_map_unavailable_or_unsupported_local_signals(self) -> None:
        sender = mock.Mock()

        recurring = healthy_snapshot()
        recurring["recurring"]["lastPollCompletedAt"] = instant(
            OBSERVED - dt.timedelta(seconds=301)
        )
        result, _ = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: recurring,
            homeops_sender=sender,
        )
        self.assertIn(("RECURRING_STALE", None, "CRITICAL"), signal_codes(result))

        backup = advance(healthy_snapshot(), 60)
        backup["backup"]["ageSeconds"] = 7 * 60 * 60
        result, _ = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: backup,
            homeops_sender=sender,
        )
        self.assertIn(("BACKUP_STALE", None, "CRITICAL"), signal_codes(result))

        unavailable = advance(healthy_snapshot(), 120)
        unavailable["filesystem"] = {
            "state": "UNAVAILABLE",
            "capacityBytes": None,
            "availableBytes": None,
            "usedPercent": None,
        }
        result, _ = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: unavailable,
            homeops_sender=sender,
        )
        self.assertIn(("FILESYSTEM_UNAVAILABLE", None, "CRITICAL"), signal_codes(result))

        first_failure = advance(healthy_snapshot(), 180)
        first_failure["services"]["web"]["health"] = "UNHEALTHY"
        first_failure["origin"] = {"reachable": True, "healthzStatus": 503}
        monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: first_failure,
            homeops_sender=sender,
        )
        second_failure = advance(first_failure, 60)
        result, _ = monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: second_failure,
            homeops_sender=sender,
        )
        self.assertIn(("SERVICE_DOWN", "web", "CRITICAL"), signal_codes(result))
        self.assertIn(("ORIGIN_DOWN", None, "CRITICAL"), signal_codes(result))
        sender.assert_not_called()

    def test_should_persist_and_retry_same_pending_alert_before_snapshot(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["filesystem"]["usedPercent"] = 80.0

        def fail_after_pending(
            _reporter: monitor_worker.HomeOpsReporter, payload: dict
        ) -> None:
            stored = monitor_worker.MonitorStateStore(self.state_directory).load()
            self.assertEqual(stored["homeOpsDisk"]["pendingSignal"], payload)
            raise monitor_worker.ReporterError("synthetic")

        with self.assertRaises(monitor_worker.ReporterError):
            monitor_worker.run_monitor(
                repo_root=self.repo_root,
                project_name="our-ledger",
                env_file="/synthetic/env",
                backup_directory=str(self.backup_directory),
                state_directory_value=str(self.state_directory),
                homeops_reporter_value=str(self.reporter_path),
                snapshot_provider=lambda *_args: snapshot,
                homeops_sender=fail_after_pending,
            )
        pending = monitor_worker.MonitorStateStore(self.state_directory).load()["homeOpsDisk"]
        self.assertIsNone(pending["activeEpisodeKey"])
        event_key = pending["pendingSignal"]["eventKey"]

        order: list[str] = []
        payloads: list[dict] = []
        provider = mock.Mock(side_effect=lambda *_args: (
            order.append("snapshot") or advance(snapshot, 60)
        ))

        def accept(_reporter: monitor_worker.HomeOpsReporter, payload: dict) -> None:
            order.append("reporter")
            payloads.append(copy.deepcopy(payload))

        monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=provider,
            homeops_sender=accept,
        )
        self.assertEqual(order, ["reporter", "snapshot"])
        self.assertEqual(payloads[0]["eventKey"], event_key)
        state = monitor_worker.MonitorStateStore(self.state_directory).load()["homeOpsDisk"]
        self.assertEqual(state["activeEpisodeKey"], "our-ledger:disk-low:1")
        self.assertIsNone(state["pendingSignal"])

    def test_should_retry_same_key_when_final_state_save_fails_after_acceptance(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["filesystem"]["usedPercent"] = 80.0
        real_save = monitor_worker.MonitorStateStore.save
        save_calls = 0
        accepted: list[dict] = []

        def flaky_save(store: monitor_worker.MonitorStateStore, state: dict) -> None:
            nonlocal save_calls
            save_calls += 1
            if save_calls == 2:
                raise OSError("synthetic final save failure")
            real_save(store, state)

        with mock.patch.object(
            monitor_worker.MonitorStateStore, "save", autospec=True, side_effect=flaky_save
        ):
            with self.assertRaises(OSError):
                monitor_worker.run_monitor(
                    repo_root=self.repo_root,
                    project_name="our-ledger",
                    env_file="/synthetic/env",
                    backup_directory=str(self.backup_directory),
                    state_directory_value=str(self.state_directory),
                    homeops_reporter_value=str(self.reporter_path),
                    snapshot_provider=lambda *_args: snapshot,
                    homeops_sender=lambda _reporter, payload: accepted.append(copy.deepcopy(payload)),
                )

        stored = monitor_worker.MonitorStateStore(self.state_directory).load()
        pending_key = stored["homeOpsDisk"]["pendingSignal"]["eventKey"]
        self.assertEqual(accepted[0]["eventKey"], pending_key)
        retried: list[dict] = []
        monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: advance(snapshot, 60),
            homeops_sender=lambda _reporter, payload: retried.append(copy.deepcopy(payload)),
        )
        self.assertEqual(retried[0]["eventKey"], pending_key)
        self.assertEqual(len(retried), 1)

    def test_should_apply_same_pending_rule_to_recovery(self) -> None:
        alert = healthy_snapshot()
        alert["filesystem"]["usedPercent"] = 80.0
        monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: alert,
            homeops_sender=lambda *_args: None,
        )
        recovery = advance(healthy_snapshot(), 60)
        recovery["filesystem"]["usedPercent"] = 79.9

        def reject_recovery(*_args: object) -> None:
            raise monitor_worker.ReporterError("synthetic")

        with self.assertRaises(monitor_worker.ReporterError):
            monitor_worker.run_monitor(
                repo_root=self.repo_root,
                project_name="our-ledger",
                env_file="/synthetic/env",
                backup_directory=str(self.backup_directory),
                state_directory_value=str(self.state_directory),
                homeops_reporter_value=str(self.reporter_path),
                snapshot_provider=lambda *_args: recovery,
                homeops_sender=reject_recovery,
            )
        stored = monitor_worker.MonitorStateStore(self.state_directory).load()["homeOpsDisk"]
        self.assertEqual(stored["activeEpisodeKey"], "our-ledger:disk-low:1")
        self.assertEqual(stored["pendingSignal"]["status"], "RECOVERED")
        event_key = stored["pendingSignal"]["eventKey"]

        retried: list[dict] = []
        monitor_worker.run_monitor(
            repo_root=self.repo_root,
            project_name="our-ledger",
            env_file="/synthetic/env",
            backup_directory=str(self.backup_directory),
            state_directory_value=str(self.state_directory),
            homeops_reporter_value=str(self.reporter_path),
            snapshot_provider=lambda *_args: advance(recovery, 60),
            homeops_sender=lambda _reporter, payload: retried.append(copy.deepcopy(payload)),
        )
        self.assertEqual(retried[0]["eventKey"], event_key)
        final = monitor_worker.MonitorStateStore(self.state_directory).load()["homeOpsDisk"]
        self.assertIsNone(final["activeEpisodeKey"])
        self.assertIsNone(final["pendingSignal"])

    def test_should_reject_reporter_overlap_before_lock_without_backup_mutation(self) -> None:
        cases: list[tuple[str, Path, Path, Path]] = []

        backup = self.root / "reporter-backup"
        self.create_valid_backup(backup)
        reporter_in_backup = backup / monitor_worker.HOMEOPS_REPORTER_FILENAME
        reporter_in_backup.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        reporter_in_backup.chmod(0o700)
        cases.append(("backup-descendant", backup, self.state_directory, reporter_in_backup))

        state = self.root / "reporter-state"
        state.mkdir(mode=0o700)
        reporter_in_state = state / monitor_worker.HOMEOPS_REPORTER_FILENAME
        reporter_in_state.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        reporter_in_state.chmod(0o700)
        cases.append(("state-descendant", self.backup_directory, state, reporter_in_state))

        for label, backup_directory, state_directory, reporter in cases:
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
                        homeops_reporter_value=str(reporter),
                        snapshot_provider=provider,
                        homeops_sender=sender,
                    )
                provider.assert_not_called()
                sender.assert_not_called()
                self.assertEqual(self.tree_fingerprint(backup_directory), before)
                self.assertFalse(os.path.lexists(state_directory / monitor_worker.LOCK_FILENAME))
                self.assertFalse(os.path.lexists(state_directory / monitor_worker.STATE_FILENAME))
                self.assertEqual(list(state_directory.glob(".monitor-state.*")), [])


class HomeOpsReporterBoundaryTest(unittest.TestCase):

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="our-ledger-homeops-reporter-test.")
        self.root = Path(self.temporary.name)
        self.repo_root = self.root / "repo"
        self.repo_root.mkdir(mode=0o700)
        self.reporter_path = self.root / monitor_worker.HOMEOPS_REPORTER_FILENAME
        self.payload = {
            "eventKey": "our-ledger:disk-low:1:alert",
            "episodeKey": "our-ledger:disk-low:1",
            "project": "our-ledger",
            "signalType": "DISK_LOW",
            "status": "ALERT",
            "observedAt": "2026-08-29T12:00:00Z",
            "availablePercent": 20.0,
            "thresholdPercent": 20,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_reporter(self, source: str) -> monitor_worker.HomeOpsReporter:
        self.reporter_path.write_text(source, encoding="utf-8")
        self.reporter_path.chmod(0o700)
        return monitor_worker.validate_homeops_reporter(
            self.repo_root, str(self.reporter_path)
        )

    def test_should_expose_homeops_reporter_cli_authority(self) -> None:
        self.assertIn("--homeops-reporter", monitor_worker.parser().format_help())

    def test_should_execute_exact_reporter_signal_with_exact_json_stdin(self) -> None:
        args_path = self.root / "args.json"
        payload_path = self.root / "payload.json"
        authority = self.write_reporter(
            "#!/usr/bin/python3\n"
            "import pathlib\n"
            "import sys\n"
            f"pathlib.Path({str(args_path)!r}).write_text(__import__('json').dumps(sys.argv[1:]), encoding='utf-8')\n"
            f"pathlib.Path({str(payload_path)!r}).write_bytes(sys.stdin.buffer.read())\n"
        )

        monitor_worker.send_homeops_signal(authority, self.payload)

        self.assertEqual(json.loads(args_path.read_text(encoding="utf-8")), ["signal"])
        self.assertEqual(
            payload_path.read_bytes(), monitor_worker._homeops_payload_bytes(self.payload)
        )

    def test_should_use_shell_false_bounded_timeout_and_suppressed_output(self) -> None:
        authority = self.write_reporter("#!/bin/sh\nexit 0\n")
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(
            monitor_worker.subprocess, "run", return_value=completed
        ) as run:
            monitor_worker.send_homeops_signal(authority, self.payload)

        self.assertEqual(run.call_args.args[0], [str(authority.path), "signal"])
        self.assertEqual(
            run.call_args.kwargs["input"], monitor_worker._homeops_payload_bytes(self.payload)
        )
        self.assertIs(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertNotIn("env", run.call_args.kwargs)
        self.assertEqual(
            run.call_args.kwargs["timeout"], monitor_worker.HOMEOPS_REPORTER_TIMEOUT_SECONDS
        )

    def test_should_fail_generically_on_nonzero_timeout_or_replaced_reporter(self) -> None:
        authority = self.write_reporter("#!/bin/sh\nexit 0\n")
        failures = (
            mock.Mock(return_value=subprocess.CompletedProcess([], 7)),
            mock.Mock(side_effect=subprocess.TimeoutExpired([str(authority.path), "signal"], 5)),
        )
        for runner in failures:
            with self.subTest(side_effect=type(runner.side_effect).__name__):
                with mock.patch.object(monitor_worker.subprocess, "run", runner):
                    with self.assertRaises(monitor_worker.ReporterError) as raised:
                        monitor_worker.send_homeops_signal(authority, self.payload)
                message = str(raised.exception)
                self.assertNotIn(str(authority.path), message)
                self.assertNotIn(self.payload["eventKey"], message)

        retired = self.root / "retired-reporter.py"
        self.reporter_path.rename(retired)
        self.reporter_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.reporter_path.chmod(0o700)
        with self.assertRaises(monitor_worker.ReporterError):
            monitor_worker.send_homeops_signal(authority, self.payload)


if __name__ == "__main__":
    unittest.main()
