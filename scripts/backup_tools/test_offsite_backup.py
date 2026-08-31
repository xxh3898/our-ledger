#!/usr/bin/env python3

from __future__ import annotations

from io import BytesIO
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from scripts.backup_tools import backup_artifact
from scripts.backup_tools import offsite_backup as contract


CREATED_AT = "2026-08-31T00:35:00Z"
SECOND_CREATED_AT = "2026-08-31T06:35:00Z"
SCHEMA_VERSION = "8"
PG_DUMP_VERSION = "pg_dump (PostgreSQL) 18.6"
SERVER_VERSION = "18.6"
SYNTHETIC_RECIPIENT = (
    "age1lvyvwawkr0mcnnnncaghunadrqkmuf9e6507x9y920xxpp866cnql7dp2z"
)
NOW = dt.datetime(2026, 8, 31, 7, 0, tzinfo=dt.timezone.utc)


class OffsiteBackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="our-ledger-offsite-unit.")).resolve()
        self.root.chmod(0o700)
        self.repo_root = self.root / "repository"
        self.repo_root.mkdir(mode=0o700)
        self.backup_directory = self.root / "local-backups"
        self.backup_directory.mkdir(mode=0o700)
        self.state_directory = self.root / "offsite-state"
        self.state_directory.mkdir(mode=0o700)
        self.icloud_root = self.root / "icloud"
        self.icloud_root.mkdir(mode=0o700)
        self.target_directory = self.icloud_root / "our-ledger"
        self.target_directory.mkdir(mode=0o700)
        self.config_path = self.root / "offsite.env"
        self.write_config()
        self.age_executable = self.root / "synthetic-age"
        self.tar_executable = self.root / "synthetic-tar"
        self.write_executable(self.age_executable, "#!/bin/sh\nexit 0\n")
        self.write_executable(self.tar_executable, "#!/bin/sh\nexit 0\n")
        self.authority = self.make_authority()
        self.first_bundle = self.commit_bundle(CREATED_AT, b"PGDMPcredential@example.invalid secret-fixture")

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def make_authority(self, **overrides: object) -> contract.OffsiteAuthority:
        values: dict[str, object] = {
            "repo_root": self.repo_root,
            "backup_directory": self.backup_directory,
            "config_path": self.config_path,
            "state_directory": self.state_directory,
            "icloud_root": self.icloud_root,
            "age_entrypoint": self.age_executable,
            "tar_executable": self.tar_executable,
            "production": False,
        }
        values.update(overrides)
        return contract.OffsiteAuthority(**values)

    def write_config(
        self,
        *,
        recipient: str = SYNTHETIC_RECIPIENT,
        target: Path | None = None,
        extra: str = "",
    ) -> None:
        destination = target or self.target_directory
        self.config_path.write_text(
            f"AGE_RECIPIENT={recipient}\n"
            f"ICLOUD_TARGET_DIRECTORY={destination}\n"
            f"{extra}",
            encoding="utf-8",
        )
        self.config_path.chmod(0o600)

    def write_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)

    def commit_bundle(self, created_at: str, content: bytes) -> Path:
        stem = backup_artifact.create_stem(created_at, SCHEMA_VERSION)
        staging = self.backup_directory / f".our-ledger_backup_{stem}.partial"
        staging.mkdir(mode=0o700)
        dump = staging / f"{stem}.dump"
        dump.write_bytes(content)
        dump.chmod(0o600)
        backup_artifact.fsync_dump_file(
            self.backup_directory, staging, dump.name
        )
        backup_artifact.write_sidecars(
            self.backup_directory,
            staging,
            dump.name,
            created_at,
            SCHEMA_VERSION,
            PG_DUMP_VERSION,
            SERVER_VERSION,
        )
        final_dump = backup_artifact.commit_bundle(
            self.backup_directory, staging, f"{stem}.backup"
        )
        return final_dump.parent

    @staticmethod
    def fake_pipeline(
        source: contract.SourceBundle,
        resolved: contract.ResolvedAuthority,
        destination_descriptor: int,
    ) -> None:
        del resolved
        payload = f"age-encrypted:{source.name}".encode("ascii")
        os.write(destination_descriptor, payload)

    def run_success(self, *, now: dt.datetime = NOW) -> dict[str, object]:
        return contract.run_offsite_backup(
            self.authority,
            pipeline_runner=self.fake_pipeline,
            now=lambda: now,
        )

    def marker(self) -> dict[str, object]:
        return json.loads(
            (self.state_directory / contract.MARKER_FILENAME).read_text(
                encoding="utf-8"
            )
        )

    def tree_fingerprint(self, root: Path) -> dict[str, tuple[object, ...]]:
        result: dict[str, tuple[object, ...]] = {}
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

    def assert_no_transaction_residue(self) -> None:
        self.assertEqual(
            list(self.state_directory.glob(".offsite-cipher.*.partial")), []
        )
        self.assertEqual(list(self.state_directory.glob(".*.partial")), [])
        self.assertEqual(list(self.target_directory.glob(".*.partial")), [])
        self.assertEqual(list(self.target_directory.glob("*.tar")), [])
        self.assertEqual(list(self.target_directory.glob("*.dump")), [])

    def test_should_publish_ciphertext_marker_and_privacy_safe_result(self) -> None:
        source_before = self.tree_fingerprint(self.backup_directory)

        result = self.run_success()

        marker = self.marker()
        final = self.target_directory / marker["ciphertextFilename"]
        self.assertEqual(result["result"], "REPLICATED")
        self.assertEqual(result["replicatedAt"], "2026-08-31T07:00:00Z")
        self.assertEqual(marker["sourceBundle"], self.first_bundle.name)
        self.assertEqual(marker["sourceCreatedAt"], CREATED_AT)
        self.assertEqual(marker["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(marker["ciphertextSizeBytes"], final.stat().st_size)
        self.assertEqual(
            marker["ciphertextSha256"],
            hashlib.sha256(final.read_bytes()).hexdigest(),
        )
        self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o600)
        self.assertEqual(
            stat.S_IMODE(
                (self.state_directory / contract.MARKER_FILENAME).stat().st_mode
            ),
            0o600,
        )
        self.assertEqual(self.tree_fingerprint(self.backup_directory), source_before)
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("credential@example.invalid", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(SYNTHETIC_RECIPIENT, rendered)
        self.assertNotIn(marker["ciphertextSha256"], rendered)
        self.assert_no_transaction_residue()

    def test_should_noop_only_when_marker_and_final_match_same_latest_source(self) -> None:
        self.run_success()
        before_state = self.tree_fingerprint(self.state_directory)
        before_target = self.tree_fingerprint(self.target_directory)

        def unexpected_pipeline(*args: object) -> None:
            raise AssertionError("idempotent no-op attempted encryption")

        result = contract.run_offsite_backup(
            self.authority,
            pipeline_runner=unexpected_pipeline,
            now=lambda: NOW + dt.timedelta(hours=1),
        )

        self.assertEqual(result["result"], "NO_OP")
        self.assertEqual(self.tree_fingerprint(self.state_directory), before_state)
        self.assertEqual(self.tree_fingerprint(self.target_directory), before_target)
        self.assert_no_transaction_residue()

    def test_should_advance_to_new_latest_source_and_preserve_previous_final(self) -> None:
        self.run_success()
        previous_marker = self.marker()
        previous_final = self.target_directory / previous_marker["ciphertextFilename"]
        previous_bytes = previous_final.read_bytes()
        second = self.commit_bundle(SECOND_CREATED_AT, b"PGDMPsecond-synthetic")

        result = self.run_success(now=NOW + dt.timedelta(hours=6))

        marker = self.marker()
        self.assertEqual(result["result"], "REPLICATED")
        self.assertEqual(marker["sourceBundle"], second.name)
        self.assertNotEqual(marker["ciphertextFilename"], previous_marker["ciphertextFilename"])
        self.assertEqual(previous_final.read_bytes(), previous_bytes)
        self.assertEqual(len(list(self.target_directory.glob("*.tar.age"))), 2)
        self.assert_no_transaction_residue()

    def test_should_preserve_unrelated_partial_and_fail_closed_on_final_collision(self) -> None:
        unrelated_partial = self.target_directory / ".operator-owned.partial"
        unrelated_partial.write_bytes(b"preserve")
        unrelated_partial.chmod(0o600)

        self.run_success()

        self.assertEqual(unrelated_partial.read_bytes(), b"preserve")
        marker = self.marker()
        marker_path = self.state_directory / contract.MARKER_FILENAME
        marker_before = marker_path.read_bytes()
        final = self.target_directory / marker["ciphertextFilename"]
        final_before = final.read_bytes()
        marker_path.unlink()
        called = False

        def pipeline(*args: object) -> None:
            nonlocal called
            called = True

        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                self.authority,
                pipeline_runner=pipeline,
                now=lambda: NOW + dt.timedelta(hours=1),
            )

        self.assertFalse(called)
        self.assertEqual(final.read_bytes(), final_before)
        self.assertEqual(unrelated_partial.read_bytes(), b"preserve")
        self.assertFalse(marker_path.exists())
        self.assertTrue(marker_before)
        self.assertEqual(
            list(self.state_directory.glob(".offsite-cipher.*.partial")), []
        )

    def test_should_not_overwrite_destination_created_at_finalization(self) -> None:
        self.run_success()
        marker_path = self.state_directory / contract.MARKER_FILENAME
        previous_marker = marker_path.read_bytes()
        previous_marker_value = self.marker()
        previous_final = (
            self.target_directory / previous_marker_value["ciphertextFilename"]
        )
        previous_final_bytes = previous_final.read_bytes()
        previous_final_identity = (
            previous_final.stat().st_dev,
            previous_final.stat().st_ino,
        )
        second = self.commit_bundle(
            SECOND_CREATED_AT, b"PGDMPfinalization-collision"
        )
        collision_final = (
            self.target_directory / contract._ciphertext_name(second.name)
        )
        collision_bytes = b"concurrent-owner-ciphertext"
        collision_identity: tuple[int, int] | None = None
        real_rename = contract._rename_no_replace

        def collide_before_rename(source: Path, destination: Path) -> None:
            nonlocal collision_identity
            if destination == collision_final:
                collision_final.write_bytes(collision_bytes)
                collision_final.chmod(0o600)
                info = collision_final.stat()
                collision_identity = (info.st_dev, info.st_ino)
            real_rename(source, destination)

        with mock.patch.object(
            contract, "_rename_no_replace", side_effect=collide_before_rename
        ):
            with self.assertRaises(contract.ContractError):
                contract.run_offsite_backup(
                    self.authority,
                    pipeline_runner=self.fake_pipeline,
                    now=lambda: NOW + dt.timedelta(hours=6),
                )

        self.assertIsNotNone(collision_identity)
        self.assertEqual(collision_final.read_bytes(), collision_bytes)
        collision_info = collision_final.stat()
        self.assertEqual(
            (collision_info.st_dev, collision_info.st_ino), collision_identity
        )
        self.assertEqual(marker_path.read_bytes(), previous_marker)
        self.assertEqual(previous_final.read_bytes(), previous_final_bytes)
        previous_final_info = previous_final.stat()
        self.assertEqual(
            (previous_final_info.st_dev, previous_final_info.st_ino),
            previous_final_identity,
        )
        self.assert_no_transaction_residue()

    def test_should_report_missing_fresh_stale_and_invalid_without_mutation(self) -> None:
        before = self.tree_fingerprint(self.state_directory)
        missing = contract.offsite_status(self.authority, now=lambda: NOW)
        self.assertEqual(missing["state"], "MISSING")
        self.assertEqual(self.tree_fingerprint(self.state_directory), before)

        self.run_success()
        fresh = contract.offsite_status(
            self.authority, now=lambda: NOW + dt.timedelta(hours=8)
        )
        stale = contract.offsite_status(
            self.authority, now=lambda: NOW + dt.timedelta(hours=8, seconds=1)
        )
        self.assertEqual(fresh["state"], "FRESH")
        self.assertEqual(fresh["ageSeconds"], contract.FRESHNESS_GRACE_SECONDS)
        self.assertEqual(stale["state"], "STALE")

        marker = self.marker()
        final = self.target_directory / marker["ciphertextFilename"]
        final.write_bytes(b"tampered")
        final.chmod(0o600)
        invalid = contract.offsite_status(
            self.authority, now=lambda: NOW + dt.timedelta(hours=1)
        )
        self.assertEqual(invalid["state"], "INVALID")
        rendered = json.dumps(invalid, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(marker["ciphertextFilename"], rendered)
        self.assertNotIn(marker["ciphertextSha256"], rendered)

    def test_should_reject_invalid_latest_authority_without_creating_state(self) -> None:
        marker_path = self.backup_directory / "last-success.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["sha256"] = "0" * 64
        marker_path.write_text(
            json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8"
        )
        marker_path.chmod(0o600)
        unrelated = self.backup_directory / "unrelated.txt"
        unrelated.write_text("preserve\n", encoding="utf-8")
        unrelated.chmod(0o600)
        backup_before = self.tree_fingerprint(self.backup_directory)

        with self.assertRaises(contract.ContractError):
            self.run_success()

        self.assertEqual(self.tree_fingerprint(self.backup_directory), backup_before)
        self.assertFalse(
            (self.state_directory / contract.MARKER_FILENAME).exists()
        )
        self.assertEqual(list(self.target_directory.iterdir()), [])
        self.assert_no_transaction_residue()

    def test_should_reject_symlink_incomplete_and_foreign_as_latest_source(self) -> None:
        original_marker = self.backup_directory / "last-success.json"
        marker = json.loads(original_marker.read_text(encoding="utf-8"))
        original_marker.unlink()
        symlink_bundle = self.backup_directory / marker["bundleDirectory"]
        real_bundle = self.root / "moved.backup"
        symlink_bundle.rename(real_bundle)
        symlink_bundle.symlink_to(real_bundle, target_is_directory=True)
        partial = self.backup_directory / ".interrupted.partial"
        partial.mkdir(mode=0o700)
        foreign = self.backup_directory / "foreign.backup"
        foreign.write_text("foreign\n", encoding="utf-8")
        foreign.chmod(0o600)
        original_marker.write_text(json.dumps(marker) + "\n", encoding="utf-8")
        original_marker.chmod(0o600)

        with self.assertRaises(contract.ContractError):
            self.run_success()

        self.assertTrue(symlink_bundle.is_symlink())
        self.assertTrue(partial.exists())
        self.assertTrue(foreign.exists())
        self.assertEqual(list(self.target_directory.iterdir()), [])

    def test_should_reject_unsafe_config_and_private_identity(self) -> None:
        invalid_contents = (
            "AGE_RECIPIENT=invalid\n"
            f"ICLOUD_TARGET_DIRECTORY={self.target_directory}\n",
            f"AGE_RECIPIENT={SYNTHETIC_RECIPIENT}\n"
            f"ICLOUD_TARGET_DIRECTORY={self.target_directory}\n"
            "AGE_IDENTITY=AGE-SECRET-KEY-PRIVATE\n",
            f"AGE_RECIPIENT={SYNTHETIC_RECIPIENT}\n"
            f"ICLOUD_TARGET_DIRECTORY={self.target_directory}\n\n",
        )
        for content in invalid_contents:
            with self.subTest(content=content[:20]):
                self.config_path.write_text(content, encoding="utf-8")
                self.config_path.chmod(0o600)
                with self.assertRaises(contract.ContractError):
                    self.run_success()
                self.assertFalse(
                    (self.state_directory / contract.LOCK_FILENAME).exists()
                )
                self.assertEqual(list(self.target_directory.iterdir()), [])

        self.write_config()
        self.config_path.chmod(0o644)
        with self.assertRaises(contract.ContractError):
            self.run_success()

        self.config_path.chmod(0o600)
        hardlink = self.root / "hardlinked-offsite.env"
        os.link(self.config_path, hardlink)
        authority = self.make_authority(config_path=hardlink)
        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                authority, pipeline_runner=self.fake_pipeline, now=lambda: NOW
            )

    def test_should_reject_path_overlap_symlink_and_unexpected_state_prelock(self) -> None:
        cases: list[tuple[str, contract.OffsiteAuthority]] = []
        cases.append(
            (
                "state-equals-backup",
                self.make_authority(state_directory=self.backup_directory),
            )
        )

        state_parent = self.root / "state-parent"
        state_parent.mkdir(mode=0o700)
        backup_child = state_parent / "backups"
        backup_child.mkdir(mode=0o700)
        cases.append(
            (
                "state-ancestor-backup",
                self.make_authority(
                    state_directory=state_parent,
                    backup_directory=backup_child,
                ),
            )
        )

        backup_parent = self.root / "backup-parent"
        backup_parent.mkdir(mode=0o700)
        state_child = backup_parent / "state"
        state_child.mkdir(mode=0o700)
        cases.append(
            (
                "state-descendant-backup",
                self.make_authority(
                    backup_directory=backup_parent,
                    state_directory=state_child,
                ),
            )
        )

        backup_before = self.tree_fingerprint(self.backup_directory)
        for label, authority in cases:
            called = False

            def pipeline(*args: object) -> None:
                nonlocal called
                called = True

            with self.subTest(label=label):
                with self.assertRaises(contract.ContractError):
                    contract.run_offsite_backup(
                        authority, pipeline_runner=pipeline, now=lambda: NOW
                    )
                self.assertFalse(called)
                self.assertFalse(
                    (Path(authority.state_directory) / contract.LOCK_FILENAME).exists()
                )
        self.assertEqual(self.tree_fingerprint(self.backup_directory), backup_before)

        target_link = self.icloud_root / "linked-target"
        target_link.symlink_to(self.target_directory, target_is_directory=True)
        self.write_config(target=target_link)
        called = False

        def symlink_pipeline(*args: object) -> None:
            nonlocal called
            called = True

        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                self.make_authority(),
                pipeline_runner=symlink_pipeline,
                now=lambda: NOW,
            )
        self.assertFalse(called)
        self.assertFalse((self.state_directory / contract.LOCK_FILENAME).exists())

        self.write_config()
        unexpected = self.state_directory / "unexpected.txt"
        unexpected.write_text("preserve\n", encoding="utf-8")
        unexpected.chmod(0o600)
        with self.assertRaises(contract.ContractError):
            self.run_success()
        self.assertFalse((self.state_directory / contract.LOCK_FILENAME).exists())
        self.assertTrue(unexpected.exists())

    def test_should_preserve_previous_authority_across_injected_failures(self) -> None:
        self.run_success()
        previous_marker = (
            self.state_directory / contract.MARKER_FILENAME
        ).read_bytes()
        previous_target = self.tree_fingerprint(self.target_directory)
        self.commit_bundle(SECOND_CREATED_AT, b"PGDMPsecond-for-failure")
        unrelated = self.target_directory / "operator-note.bin"
        unrelated.write_bytes(b"preserve")
        unrelated.chmod(0o600)
        baseline_target = self.tree_fingerprint(self.target_directory)
        points = (
            "before_staging_fsync",
            "after_staging_hash",
            "before_ciphertext_copy",
            "before_partial_fsync",
            "after_partial_hash",
            "before_final_rename",
            "after_final_rename",
            "after_final_verify",
            "before_marker_replace",
        )

        for point in points:
            with self.subTest(point=point):
                def fail_at(candidate: str, *, expected: str = point) -> None:
                    if candidate == expected:
                        raise contract.ContractError("injected failure")

                with self.assertRaises(contract.ContractError):
                    contract.run_offsite_backup(
                        self.authority,
                        pipeline_runner=self.fake_pipeline,
                        fault=fail_at,
                        now=lambda: NOW + dt.timedelta(hours=6),
                    )
                self.assertEqual(
                    (self.state_directory / contract.MARKER_FILENAME).read_bytes(),
                    previous_marker,
                )
                self.assertEqual(
                    self.tree_fingerprint(self.target_directory), baseline_target
                )
                self.assert_no_transaction_residue()

        self.assertTrue(previous_target.items() <= baseline_target.items())
        self.assertEqual(unrelated.read_bytes(), b"preserve")

    def test_should_rollback_new_marker_and_final_when_staging_cleanup_fails(self) -> None:
        self.run_success()
        previous_marker_path = self.state_directory / contract.MARKER_FILENAME
        previous_marker = previous_marker_path.read_bytes()
        previous_target = self.tree_fingerprint(self.target_directory)
        self.commit_bundle(SECOND_CREATED_AT, b"PGDMPcleanup-failure")
        real_unlink = contract._unlink_owned
        failure_count = 0

        def fail_first_staging_cleanup(
            path: Path, identity: tuple[int, int], label: str
        ) -> None:
            nonlocal failure_count
            if label == "local ciphertext staging" and failure_count == 0:
                failure_count += 1
                raise contract.ContractError("injected staging cleanup failure")
            real_unlink(path, identity, label)

        with mock.patch.object(
            contract, "_unlink_owned", side_effect=fail_first_staging_cleanup
        ):
            with self.assertRaises(contract.ContractError):
                contract.run_offsite_backup(
                    self.authority,
                    pipeline_runner=self.fake_pipeline,
                    now=lambda: NOW + dt.timedelta(hours=6),
                )

        self.assertEqual(previous_marker_path.read_bytes(), previous_marker)
        self.assertEqual(self.tree_fingerprint(self.target_directory), previous_target)
        self.assert_no_transaction_residue()

    def test_should_fail_closed_for_pipeline_copy_hash_and_source_drift(self) -> None:
        failure_runner = mock.Mock(side_effect=contract.ContractError("pipeline failed"))
        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                self.authority,
                pipeline_runner=failure_runner,
                now=lambda: NOW,
            )
        self.assert_no_transaction_residue()

        def empty_pipeline(*args: object) -> None:
            del args

        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                self.authority,
                pipeline_runner=empty_pipeline,
                now=lambda: NOW,
            )
        self.assert_no_transaction_residue()

        with mock.patch.object(
            contract,
            "_copy_ciphertext",
            return_value=(1, "0" * 64),
        ):
            with self.assertRaises(contract.ContractError):
                self.run_success()
        self.assert_no_transaction_residue()

        source_file = next(self.first_bundle.glob("*.json"))

        def drift_pipeline(
            source: contract.SourceBundle,
            resolved: contract.ResolvedAuthority,
            destination_descriptor: int,
        ) -> None:
            self.fake_pipeline(source, resolved, destination_descriptor)
            info = source_file.stat()
            os.utime(
                source_file,
                ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000),
            )

        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                self.authority,
                pipeline_runner=drift_pipeline,
                now=lambda: NOW,
            )
        self.assertTrue(source_file.exists())
        self.assert_no_transaction_residue()

    def test_should_fail_closed_when_tar_or_age_process_fails_or_times_out(self) -> None:
        forwarding_age = self.root / "forwarding-age"
        self.write_executable(
            forwarding_age,
            "#!/bin/sh\nshift 2\nexec /bin/cat\n",
        )
        tar_failure = self.make_authority(
            age_entrypoint=forwarding_age,
            tar_executable=Path("/usr/bin/false"),
        )
        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(tar_failure, now=lambda: NOW)
        self.assert_no_transaction_residue()

        age_failure = self.make_authority(
            age_entrypoint=Path("/usr/bin/false"),
            tar_executable=Path("/usr/bin/true"),
        )
        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(age_failure, now=lambda: NOW)
        self.assert_no_transaction_residue()

        truncating_age = self.root / "truncating-age"
        self.write_executable(
            truncating_age,
            "#!/bin/sh\nprintf 'truncated-ciphertext'\nexit 1\n",
        )
        truncated_failure = self.make_authority(
            age_entrypoint=truncating_age,
            tar_executable=Path("/usr/bin/true"),
        )
        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(truncated_failure, now=lambda: NOW)
        self.assert_no_transaction_residue()

        sleeping_age = self.root / "sleeping-age"
        self.write_executable(sleeping_age, "#!/bin/sh\nexec /bin/sleep 10\n")
        timeout_authority = self.make_authority(
            age_entrypoint=sleeping_age,
            tar_executable=Path("/usr/bin/true"),
        )
        with mock.patch.object(contract, "PIPELINE_TIMEOUT_SECONDS", 0.01):
            with self.assertRaises(contract.ContractError):
                contract.run_offsite_backup(timeout_authority, now=lambda: NOW)
        self.assert_no_transaction_residue()

    def test_should_reject_missing_binary_and_mutated_existing_final(self) -> None:
        missing = self.make_authority(age_entrypoint=self.root / "missing-age")
        with self.assertRaises(contract.ContractError):
            contract.run_offsite_backup(
                missing, pipeline_runner=self.fake_pipeline, now=lambda: NOW
            )
        self.assertFalse((self.state_directory / contract.LOCK_FILENAME).exists())

        self.run_success()
        marker_before = (
            self.state_directory / contract.MARKER_FILENAME
        ).read_bytes()
        marker = self.marker()
        final = self.target_directory / marker["ciphertextFilename"]
        final.write_bytes(b"mutated")
        final.chmod(0o600)
        with self.assertRaises(contract.ContractError):
            self.run_success()
        self.assertEqual(
            (self.state_directory / contract.MARKER_FILENAME).read_bytes(),
            marker_before,
        )
        self.assertEqual(final.read_bytes(), b"mutated")
        self.assert_no_transaction_residue()

    def test_should_encrypt_and_decrypt_real_age_tar_stream(self) -> None:
        age_value = os.environ.get("OUR_LEDGER_TEST_AGE_BINARY", "")
        keygen_value = os.environ.get("OUR_LEDGER_TEST_AGE_KEYGEN_BINARY", "")
        required = os.environ.get("OUR_LEDGER_REQUIRE_AGE_ROUNDTRIP") == "1"
        if not age_value or not keygen_value:
            if required:
                self.fail("real age roundtrip binary authority is missing")
            self.skipTest("real age roundtrip is exercised by verify-offsite-backup.sh")
        age = Path(age_value).resolve(strict=True)
        keygen = Path(keygen_value).resolve(strict=True)
        identity = self.root / "synthetic-age-identity.txt"
        generated = subprocess.run(
            [str(keygen), "-o", str(identity)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        self.assertEqual(generated.returncode, 0)
        identity.chmod(0o600)
        recipient_result = subprocess.run(
            [str(keygen), "-y", str(identity)],
            check=False,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(recipient_result.returncode, 0)
        recipient = recipient_result.stdout.decode("ascii").strip()
        self.assertRegex(recipient, contract.AGE_X25519_RECIPIENT_PATTERN)
        self.write_config(recipient=recipient)
        real_authority = self.make_authority(
            age_entrypoint=age,
            tar_executable=Path("/usr/bin/bsdtar")
            if Path("/usr/bin/bsdtar").exists()
            else Path("/usr/bin/tar"),
        )

        result = contract.run_offsite_backup(real_authority, now=lambda: NOW)

        self.assertEqual(result["result"], "REPLICATED")
        marker = self.marker()
        final = self.target_directory / marker["ciphertextFilename"]
        decrypted = subprocess.run(
            [str(age), "-d", "-i", str(identity), str(final)],
            check=False,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(decrypted.returncode, 0)
        expected: dict[str, str] = {}
        for source in self.first_bundle.iterdir():
            expected[f"{self.first_bundle.name}/{source.name}"] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
        actual: dict[str, str] = {}
        with tarfile.open(fileobj=BytesIO(decrypted.stdout), mode="r:") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                self.assertIsNotNone(extracted)
                assert extracted is not None
                actual[member.name] = hashlib.sha256(extracted.read()).hexdigest()
        self.assertEqual(actual, expected)
        self.assertGreater(final.stat().st_size, 0)
        self.assertEqual(
            hashlib.sha256(final.read_bytes()).hexdigest(),
            marker["ciphertextSha256"],
        )
        self.assertNotIn(b"credential@example.invalid", final.read_bytes())
        self.assertNotIn(b"secret-fixture", final.read_bytes())
        self.assert_no_transaction_residue()


if __name__ == "__main__":
    unittest.main()
