#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

import backup_artifact as contract


CREATED_AT = "2026-08-29T03:15:00Z"
SCHEMA_VERSION = "8"
PG_DUMP_VERSION = "pg_dump (PostgreSQL) 18.6"
SERVER_VERSION = "18.6"


class BackupArtifactTest(unittest.TestCase):

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="our-ledger-backup-unit.")).resolve()
        self.root.chmod(0o700)
        self.repo_root = self.root / "repository"
        self.repo_root.mkdir(mode=0o700)
        self.env_file = self.root / "production.env"
        self.env_file.write_text("POSTGRES_PASSWORD=synthetic\n", encoding="utf-8")
        self.env_file.chmod(0o600)
        self.backup_directory = self.root / "dedicated-backups"
        self.backup_directory.mkdir(mode=0o700)

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def stage_bundle(
        self,
        *,
        dump_content: bytes = b"PGDMPsynthetic-custom-archive",
        created_at: str = CREATED_AT,
        schema_version: str = SCHEMA_VERSION,
    ) -> tuple[Path, str]:
        stem = contract.create_stem(created_at, schema_version)
        staging = self.backup_directory / f".our-ledger_backup_{stem}.partial"
        staging.mkdir(mode=0o700)
        dump = staging / f"{stem}.dump"
        dump.write_bytes(dump_content)
        dump.chmod(0o600)
        contract.write_sidecars(
            self.backup_directory,
            staging,
            dump.name,
            created_at,
            schema_version,
            PG_DUMP_VERSION,
            SERVER_VERSION,
        )
        return staging, stem

    def commit_valid_bundle(self) -> tuple[Path, str]:
        staging, stem = self.stage_bundle()
        dump = contract.commit_bundle(
            self.backup_directory,
            staging,
            f"{stem}.backup",
        )
        return dump.parent, stem

    def copied_bundle(self, bundle: Path, label: str) -> Path:
        parent = self.root / label
        parent.mkdir(mode=0o700)
        copied = parent / bundle.name
        shutil.copytree(bundle, copied)
        copied.chmod(0o700)
        for item in copied.iterdir():
            item.chmod(0o600)
        return copied

    def test_should_validate_canonical_owner_only_paths(self) -> None:
        self.assertEqual(
            contract.validate_env_path(str(self.repo_root), str(self.env_file)),
            self.env_file,
        )
        self.assertEqual(
            contract.validate_backup_directory(
                str(self.repo_root), str(self.backup_directory)
            ),
            self.backup_directory,
        )

    def test_should_reject_missing_relative_traversal_and_protected_paths(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(str(self.repo_root), "relative/backups")
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(
                str(self.repo_root), str(self.root / "missing")
            )
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(
                str(self.repo_root), f"{self.root}/dedicated-backups/../dedicated-backups"
            )
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(str(self.repo_root), "/")
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(
                str(self.repo_root), str(self.repo_root)
            )

    def test_should_reject_symlink_and_permissive_or_unwritable_paths(self) -> None:
        backup_link = self.root / "backup-link"
        backup_link.symlink_to(self.backup_directory, target_is_directory=True)
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(str(self.repo_root), str(backup_link))

        self.backup_directory.chmod(0o755)
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(
                str(self.repo_root), str(self.backup_directory)
            )
        self.backup_directory.chmod(0o500)
        with self.assertRaises(contract.ContractError):
            contract.validate_backup_directory(
                str(self.repo_root), str(self.backup_directory)
            )

    def test_should_reject_unsafe_env_file(self) -> None:
        inside_repo = self.repo_root / "production.env"
        inside_repo.write_text("POSTGRES_PASSWORD=synthetic\n", encoding="utf-8")
        inside_repo.chmod(0o600)
        with self.assertRaises(contract.ContractError):
            contract.validate_env_path(str(self.repo_root), str(inside_repo))

        env_link = self.root / "production-link.env"
        env_link.symlink_to(self.env_file)
        with self.assertRaises(contract.ContractError):
            contract.validate_env_path(str(self.repo_root), str(env_link))

        self.env_file.chmod(0o644)
        with self.assertRaises(contract.ContractError):
            contract.validate_env_path(str(self.repo_root), str(self.env_file))

    def test_should_commit_atomic_bundle_and_latest_marker(self) -> None:
        bundle, stem = self.commit_valid_bundle()
        metadata = contract.verify_bundle(bundle)
        self.assertEqual(metadata["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(metadata["dumpFilename"], f"{stem}.dump")
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o700)
        self.assertTrue(
            all(stat.S_IMODE(item.stat().st_mode) == 0o600 for item in bundle.iterdir())
        )

        marker_path = self.backup_directory / "last-success.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        self.assertEqual(marker["bundleDirectory"], bundle.name)
        self.assertEqual(marker["sha256"], metadata["sha256"])
        self.assertEqual(stat.S_IMODE(marker_path.stat().st_mode), 0o600)

        inventory = contract.inventory(self.backup_directory)
        self.assertTrue(inventory["lastSuccessValid"])
        self.assertEqual(inventory["valid"][0]["bundleDirectory"], bundle.name)
        self.assertTrue(inventory["valid"][0]["isLatest"])

    def test_should_preserve_previous_marker_and_bundle_on_collision(self) -> None:
        previous_bundle, _ = self.commit_valid_bundle()
        marker_path = self.backup_directory / "last-success.json"
        previous_marker = marker_path.read_bytes()
        previous_dump = next(previous_bundle.glob("*.dump")).read_bytes()

        staging, stem = self.stage_bundle(created_at="2026-08-29T03:16:00Z")
        collision = self.backup_directory / f"{stem}.backup"
        collision.mkdir(mode=0o700)
        with self.assertRaises(contract.ContractError):
            contract.commit_bundle(
                self.backup_directory,
                staging,
                collision.name,
            )

        self.assertEqual(marker_path.read_bytes(), previous_marker)
        self.assertEqual(next(previous_bundle.glob("*.dump")).read_bytes(), previous_dump)
        self.assertTrue(staging.exists())
        contract.cleanup_staging(self.backup_directory, staging)
        collision.rmdir()

    def test_should_reject_zero_truncated_corrupt_checksum_and_metadata(self) -> None:
        bundle, stem = self.commit_valid_bundle()
        dump_name = f"{stem}.dump"

        zero = self.copied_bundle(bundle, "zero")
        (zero / dump_name).write_bytes(b"")
        with self.assertRaises(contract.ContractError):
            contract.verify_bundle(zero)

        truncated = self.copied_bundle(bundle, "truncated")
        (truncated / dump_name).write_bytes(b"PG")
        with self.assertRaises(contract.ContractError):
            contract.verify_bundle(truncated)

        corrupt = self.copied_bundle(bundle, "corrupt")
        with (corrupt / dump_name).open("ab") as target:
            target.write(b"tampered")
        with self.assertRaises(contract.ContractError):
            contract.verify_bundle(corrupt)

        checksum = self.copied_bundle(bundle, "checksum")
        (checksum / f"{stem}.sha256").write_text(
            f"{'0' * 64}  {dump_name}\n", encoding="ascii"
        )
        with self.assertRaises(contract.ContractError):
            contract.verify_bundle(checksum)

        metadata_copy = self.copied_bundle(bundle, "metadata")
        metadata_path = metadata_copy / f"{stem}.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["sizeBytes"] += 1
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(contract.ContractError):
            contract.verify_bundle(metadata_copy)

    def test_should_inventory_incomplete_invalid_and_foreign_entries_without_deleting(self) -> None:
        self.commit_valid_bundle()
        incomplete = self.backup_directory / ".our-ledger_backup_interrupted.partial"
        incomplete.mkdir(mode=0o700)
        invalid = self.backup_directory / (
            "our-ledger_production_20260829T031700Z_v8_aaaaaaaaaaaa.backup"
        )
        invalid.mkdir(mode=0o700)
        foreign = self.backup_directory / "notes.txt"
        foreign.write_text("not a backup\n", encoding="utf-8")
        foreign.chmod(0o600)

        inventory = contract.inventory(self.backup_directory)
        self.assertIn(incomplete.name, inventory["incomplete"])
        self.assertIn(invalid.name, inventory["invalid"])
        self.assertIn(foreign.name, inventory["foreign"])
        self.assertTrue(incomplete.exists())
        self.assertTrue(invalid.exists())
        self.assertTrue(foreign.exists())

    def test_should_cleanup_only_strict_direct_partial_directory(self) -> None:
        staging, _ = self.stage_bundle()
        contract.cleanup_staging(self.backup_directory, staging)
        self.assertFalse(staging.exists())

        unsafe = self.backup_directory / "unsafe.partial"
        unsafe.mkdir(mode=0o700)
        with self.assertRaises(contract.ContractError):
            contract.cleanup_staging(self.backup_directory, unsafe)
        self.assertTrue(unsafe.exists())

    def test_should_validate_exact_postgres_container_boundary(self) -> None:
        compose_file = self.repo_root / "compose.prod.yaml"
        compose_file.write_text("services: {}\n", encoding="utf-8")
        compose_file.chmod(0o600)
        project = "our-ledger-production"
        image = "postgres:18.6-alpine3.23@sha256:fixture"
        payload = [
            {
                "Config": {
                    "Image": image,
                    "Labels": {
                        "com.docker.compose.project": project,
                        "com.docker.compose.service": "postgres",
                        "com.docker.compose.project.config_files": str(compose_file),
                    },
                },
                "State": {"Status": "running", "Health": {"Status": "healthy"}},
                "HostConfig": {"PortBindings": {}, "NetworkMode": f"{project}_database"},
                "Mounts": [
                    {
                        "Type": "volume",
                        "Destination": "/var/lib/postgresql",
                        "Name": f"{project}_postgres-data",
                    }
                ],
                "NetworkSettings": {
                    "Networks": {f"{project}_database": {}}
                },
            }
        ]
        contract.check_postgres_container(payload, project, compose_file, image)

        payload[0]["State"]["Health"]["Status"] = "unhealthy"
        with self.assertRaises(contract.ContractError):
            contract.check_postgres_container(payload, project, compose_file, image)


if __name__ == "__main__":
    unittest.main(verbosity=2)
