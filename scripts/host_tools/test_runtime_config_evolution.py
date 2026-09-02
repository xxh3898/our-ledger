from __future__ import annotations

import io
import json
import os
import socket
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Mapping
from unittest import mock

from scripts.host_tools import host_state, production_deploy


ROOT = Path(__file__).resolve().parents[2]
REVISION_ONE = "1" * 40
REVISION_TWO = "2" * 40
DIGEST_ONE = "sha256:" + ("a" * 64)
DIGEST_TWO = "sha256:" + ("b" * 64)
LEGACY_REFERENCE_SHA256 = "16b528e1b12d038208ad07fff79c3159a8871d802b94a89e3fb1f78a9c75df93"
OFFSITE_FILES = {
    "scripts/backup_tools/offsite_backup.py": 0o600,
    "scripts/offsite-backup-production.sh": 0o700,
}
FIXED_BOOTSTRAP_FILES = {
    "scripts/backup-our-ledger-bootstrap.sh": 0o700,
    "scripts/offsite-our-ledger-bootstrap.sh": 0o700,
}
V2_FILES = {
    **host_state.LEGACY_RELEASE_FILES,
    **OFFSITE_FILES,
    **FIXED_BOOTSTRAP_FILES,
}


class RuntimeConfigEvolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary.name).resolve()
        self.paths = host_state.HostPaths(self.temp / "host")
        host_state.initialize_layout(self.paths)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_frozen_legacy_profile_and_hash_match_old_worker(self) -> None:
        source = self._legacy_release("legacy-reference")

        self.assertEqual(len(host_state.LEGACY_RELEASE_FILES), 20)
        self.assertNotIn(host_state.RUNTIME_MANIFEST, host_state.LEGACY_RELEASE_FILES)
        self.assertTrue(OFFSITE_FILES.keys().isdisjoint(host_state.LEGACY_RELEASE_FILES))
        self.assertTrue(
            FIXED_BOOTSTRAP_FILES.keys().isdisjoint(host_state.LEGACY_RELEASE_FILES)
        )
        self.assertEqual(
            host_state.release_content_sha256(source),
            LEGACY_REFERENCE_SHA256,
        )

    def test_repository_manifest_exact_bytes_match_v2_profile(self) -> None:
        manifest_path = ROOT / host_state.RUNTIME_MANIFEST
        manifest_value = {
            "formatVersion": 2,
            "project": "our-ledger",
            "files": [
                {"path": relative, "mode": f"{mode:04o}"}
                for relative, mode in sorted(V2_FILES.items())
            ],
        }
        expected_bytes = (
            json.dumps(manifest_value, ensure_ascii=True, indent=2).encode("utf-8")
            + b"\n"
        )

        self.assertEqual(manifest_path.read_bytes(), expected_bytes)
        profile = host_state.parse_runtime_manifest(expected_bytes)
        self.assertEqual(profile.format_version, 2)
        self.assertEqual(profile.file_modes, V2_FILES)
        self.assertEqual(len(profile.file_modes), 24)
        self.assertEqual(
            profile.directories,
            {
                "infra",
                "infra/nginx",
                "scripts",
                "scripts/backup_tools",
                "scripts/host_tools",
                "scripts/release_tools",
                "scripts/status_tools",
            },
        )

    def test_legacy_state_and_inspect_remain_byte_compatible_and_read_only(self) -> None:
        source = self._legacy_release("legacy-state")
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock, source, DIGEST_ONE, REVISION_ONE)
            host_state.begin_pending(self.paths, lock, identity)
            host_state.commit_pending(self.paths, lock)
        before = self._tree_fingerprint(self.paths.runtime_root)

        with host_state.OperationLock(self.paths) as lock:
            result = host_state.inspect_state(self.paths, lock)

        self.assertEqual(result["status"], "READY")
        self.assertEqual(
            host_state.ReleaseIdentity.from_json(result["current"]),
            identity,
        )
        self.assertEqual(self._tree_fingerprint(self.paths.runtime_root), before)
        self.assertEqual(
            set(json.loads(self.paths.state_file.read_text(encoding="utf-8"))),
            {"formatVersion", "project", "current", "previous"},
        )

    def test_bridge_transitions_from_legacy_to_manifested_v2_archive(self) -> None:
        legacy = self._legacy_release("legacy-current")
        with host_state.OperationLock(self.paths) as lock:
            previous = self._stage(lock, legacy, DIGEST_ONE, REVISION_ONE)
            host_state.begin_pending(self.paths, lock, previous)
            host_state.commit_pending(self.paths, lock)

        v2_source = self._v2_release("v2-candidate")
        archive = self.temp / "v2-runtime.tar"
        self._write_archive(v2_source, archive)
        extracted = self.temp / "v2-extracted"
        production_deploy._extract_verified_runtime(archive, extracted)

        with host_state.OperationLock(self.paths) as lock:
            candidate = self._stage(lock, extracted, DIGEST_TWO, REVISION_TWO)
            host_state.begin_pending(self.paths, lock, candidate)
            host_state.commit_pending(self.paths, lock)
            result = host_state.inspect_state(self.paths, lock)

        current = self.paths.releases / candidate.release_name
        profile = host_state._validate_release(current)
        self.assertEqual(profile.format_version, 2)
        self.assertEqual(profile.file_modes, V2_FILES)
        self.assertEqual(result["current"], candidate.to_json())
        state = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["previous"], previous.to_json())
        self.assertNotEqual(
            candidate.runtime_config_content_sha256,
            previous.runtime_config_content_sha256,
        )

    def test_manifest_exact_bytes_are_part_of_v2_content_identity(self) -> None:
        compact = self._v2_release("compact")
        expanded = self._v2_release("expanded")
        value = json.loads(
            (expanded / host_state.RUNTIME_MANIFEST).read_text(encoding="utf-8")
        )
        (expanded / host_state.RUNTIME_MANIFEST).write_text(
            json.dumps(value, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (expanded / host_state.RUNTIME_MANIFEST).chmod(0o600)
        for relative in V2_FILES:
            (expanded / relative).write_bytes((compact / relative).read_bytes())

        self.assertNotEqual(
            host_state.release_content_sha256(compact),
            host_state.release_content_sha256(expanded),
        )

    def test_strict_manifest_schema_and_path_failure_matrix(self) -> None:
        valid = self._manifest_bytes(V2_FILES)
        valid_value = json.loads(valid)
        invalid_payloads = {
            "empty": b"",
            "duplicate-top-level-key": (
                b'{"formatVersion":2,"formatVersion":2,"project":"our-ledger",'
                b'"files":[{"path":"compose.yaml","mode":"0600"}]}'
            ),
            "duplicate-entry-key": (
                b'{"formatVersion":2,"project":"our-ledger","files":['
                b'{"path":"compose.yaml","path":"scripts/x","mode":"0600"}]}'
            ),
            "unknown-top-level": self._json_bytes({**valid_value, "extra": True}),
            "invalid-version": self._json_bytes({**valid_value, "formatVersion": 3}),
            "boolean-version": self._json_bytes({**valid_value, "formatVersion": True}),
            "invalid-project": self._json_bytes({**valid_value, "project": "other"}),
            "empty-files": self._json_bytes({**valid_value, "files": []}),
            "unknown-entry": self._manifest_with_entry("compose.yaml", "0600", extra=True),
            "invalid-mode": self._manifest_with_entry("compose.yaml", "0644"),
            "non-string-mode": self._manifest_with_entry("compose.yaml", 600),
            "absolute-path": self._manifest_with_entry("/compose.yaml", "0600"),
            "parent-path": self._manifest_with_entry("scripts/../compose.yaml", "0600"),
            "dot-path": self._manifest_with_entry("./compose.yaml", "0600"),
            "empty-segment": self._manifest_with_entry("scripts//x", "0600"),
            "backslash-path": self._manifest_with_entry("scripts\\x", "0600"),
            "nul-path": self._manifest_with_entry("scripts/\x00x", "0600"),
            "manifest-self-entry": self._manifest_with_entry(
                host_state.RUNTIME_MANIFEST,
                "0600",
            ),
            "foreign-namespace": self._manifest_with_entry("foreign/x", "0600"),
            "private-key-marker": self._manifest_with_entry(
                "scripts/-----BEGIN PRIVATE KEY-----",
                "0600",
            ),
            "duplicate-path": self._json_bytes(
                {
                    "formatVersion": 2,
                    "project": "our-ledger",
                    "files": [
                        {"path": "compose.yaml", "mode": "0600"},
                        {"path": "compose.yaml", "mode": "0600"},
                    ],
                }
            ),
            "unsorted-path": self._json_bytes(
                {
                    "formatVersion": 2,
                    "project": "our-ledger",
                    "files": [
                        {"path": "scripts/x", "mode": "0600"},
                        {"path": "compose.yaml", "mode": "0600"},
                    ],
                }
            ),
            "oversize": b" " * (host_state.MAX_RUNTIME_MANIFEST_SIZE + 1),
        }

        for name, payload in invalid_payloads.items():
            with self.subTest(name=name), self.assertRaises(host_state.ContractError):
                host_state.parse_runtime_manifest(payload)

    def test_release_tree_failure_matrix_preserves_committed_v1(self) -> None:
        committed_source = self._legacy_release("committed")
        with host_state.OperationLock(self.paths) as lock:
            committed = self._stage(lock, committed_source, DIGEST_ONE, REVISION_ONE)
            host_state.begin_pending(self.paths, lock, committed)
            host_state.commit_pending(self.paths, lock)
        before = self._tree_fingerprint(self.paths.runtime_root)

        invalid_sources = self._invalid_release_sources()
        for name, source in invalid_sources.items():
            with self.subTest(name=name):
                with self.assertRaises(host_state.ContractError):
                    host_state.release_content_sha256(source)
                with host_state.OperationLock(self.paths) as lock:
                    with self.assertRaises(host_state.ContractError):
                        self._stage(lock, source, DIGEST_TWO, REVISION_TWO)
                self.assertEqual(self._tree_fingerprint(self.paths.runtime_root), before)
                self.assertFalse(
                    any(path.name.startswith(".stage-") for path in self.paths.releases.iterdir())
                )

    def test_post_extract_v2_tamper_during_stage_fails_and_cleans_owned_stage(self) -> None:
        committed_source = self._legacy_release("stable")
        with host_state.OperationLock(self.paths) as lock:
            committed = self._stage(lock, committed_source, DIGEST_ONE, REVISION_ONE)
            host_state.begin_pending(self.paths, lock, committed)
            host_state.commit_pending(self.paths, lock)
        before = self._tree_fingerprint(self.paths.runtime_root)
        candidate_source = self._v2_release("changing-source")
        archive = self.temp / "changing-v2.tar"
        self._write_archive(candidate_source, archive)
        candidate = self.temp / "changing-extracted"
        production_deploy._extract_verified_runtime(archive, candidate)
        original_copy = host_state._copy_regular_file
        changed = False

        def copy_then_change(source: Path, destination: Path, mode: int) -> None:
            nonlocal changed
            original_copy(source, destination, mode)
            if not changed:
                changed = True
                target = candidate / "compose.yaml"
                target.write_text("changed-during-copy\n", encoding="utf-8")
                target.chmod(0o600)

        with mock.patch.object(host_state, "_copy_regular_file", copy_then_change):
            with host_state.OperationLock(self.paths) as lock:
                with self.assertRaisesRegex(
                    host_state.ContractError,
                    "source changed during staging",
                ):
                    self._stage(lock, candidate, DIGEST_TWO, REVISION_TWO)

        self.assertEqual(self._tree_fingerprint(self.paths.runtime_root), before)
        self.assertFalse(
            any(path.name.startswith(".stage-") for path in self.paths.releases.iterdir())
        )

    def test_interrupted_manifest_copy_is_bounded_abandoned_stage_only(self) -> None:
        stage_name = ".stage-" + ("f" * 32)
        stage = self.paths.releases / stage_name
        stage.mkdir(mode=0o700)
        manifest = stage / host_state.RUNTIME_MANIFEST
        manifest.write_bytes(b'{"formatVersion":')
        manifest.chmod(0o600)

        with host_state.OperationLock(self.paths) as lock:
            inspected = host_state.inspect_state(self.paths, lock)
            self.assertEqual(inspected["abandonedStages"], [stage_name])
            host_state.clear_abandoned_stage(self.paths, lock, stage_name)

        self.assertFalse(stage.exists())
        self.assertEqual(list(self.paths.releases.iterdir()), [])

    def test_archive_failure_matrix_rejects_without_extraction(self) -> None:
        source = self._v2_release("archive")
        cases: dict[str, dict[str, object]] = {
            "missing-manifest": {"omit": {host_state.RUNTIME_MANIFEST}},
            "missing-payload": {"omit": {"compose.yaml"}},
            "extra-payload": {"extra_file": "scripts/extra.py"},
            "mode-mismatch": {"mode_override": {"compose.yaml": 0o700}},
            "foreign-directory": {"extra_directory": "foreign"},
            "duplicate": {"duplicate": "compose.yaml"},
            "symlink": {"type_override": {"compose.yaml": tarfile.SYMTYPE}},
            "hardlink": {"type_override": {"compose.yaml": tarfile.LNKTYPE}},
            "device": {"type_override": {"compose.yaml": tarfile.CHRTYPE}},
            "fifo": {"type_override": {"compose.yaml": tarfile.FIFOTYPE}},
            "socket": {"type_override": {"compose.yaml": b"s"}},
            "manifest-symlink": {
                "type_override": {host_state.RUNTIME_MANIFEST: tarfile.SYMTYPE}
            },
            "manifest-fifo": {
                "type_override": {host_state.RUNTIME_MANIFEST: tarfile.FIFOTYPE}
            },
            "oversize-file": {
                "size_override": {
                    "compose.yaml": host_state.MAX_RELEASE_FILE_SIZE + 1
                }
            },
            "oversize-manifest": {
                "size_override": {
                    host_state.RUNTIME_MANIFEST: host_state.MAX_RUNTIME_MANIFEST_SIZE
                    + 1
                }
            },
            "invalid-manifest": {
                "payload_override": {
                    host_state.RUNTIME_MANIFEST: b'{"formatVersion":2}'
                }
            },
        }

        for name, options in cases.items():
            archive = self.temp / f"invalid-{name}.tar"
            self._write_archive(source, archive, **options)
            destination = self.temp / f"extract-{name}"
            with self.subTest(name=name), self.assertRaises(
                production_deploy.DeploymentError
            ):
                production_deploy._extract_verified_runtime(archive, destination)
            self.assertFalse(destination.exists())

    def test_archive_path_traversal_is_rejected_before_extraction(self) -> None:
        for name in ("runtime/../outside", "/runtime/compose.yaml"):
            archive = self.temp / f"unsafe-{len(name)}-{name.count('/')}"
            with tarfile.open(archive, "w") as bundle:
                member = tarfile.TarInfo(name)
                member.mode = 0o600
                member.size = 1
                bundle.addfile(member, io.BytesIO(b"x"))
            destination = self.temp / f"unsafe-extract-{len(name)}-{name.count('/')}"
            with self.subTest(name=name), self.assertRaises(
                production_deploy.DeploymentError
            ):
                production_deploy._extract_verified_runtime(archive, destination)
            self.assertFalse(destination.exists())

    def test_dedicated_gate_is_wired_without_external_or_production_access(self) -> None:
        gate_path = ROOT / "scripts" / "verify-runtime-config-evolution.sh"
        gate = gate_path.read_text(encoding="utf-8")
        local = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        hosted = (ROOT / ".github/workflows/full-ci.yml").read_text(encoding="utf-8")

        self.assertTrue(os.access(gate_path, os.X_OK))
        self.assertIn("--platform linux/arm64", gate)
        self.assertIn("--network none", gate)
        self.assertIn("verify-runtime-config-evolution.sh", local)
        self.assertIn("  runtime-config-evolution:\n", hosted)
        self.assertIn("run: ./scripts/verify-runtime-config-evolution.sh", hosted)
        self.assertNotRegex(
            gate,
            r"(?m)(?:^|\s)(?:curl|gh|ssh|tailscale)(?:\s|$)|"
            r"docker\s+(?:login|pull|push)|/Users/homeserver/Server",
        )

    def _invalid_release_sources(self) -> dict[str, Path]:
        sources: dict[str, Path] = {}

        legacy_extra = self._legacy_release("legacy-extra")
        target = legacy_extra / "scripts/backup_tools/offsite_backup.py"
        target.write_text("extra\n", encoding="utf-8")
        target.chmod(0o600)
        sources["legacy-offsite-without-manifest"] = legacy_extra

        missing = self._v2_release("missing")
        (missing / "compose.yaml").unlink()
        sources["v2-missing-payload"] = missing

        extra = self._v2_release("extra")
        target = extra / "scripts/extra.py"
        target.write_text("extra\n", encoding="utf-8")
        target.chmod(0o600)
        sources["v2-extra-payload"] = extra

        wrong_mode = self._v2_release("mode")
        (wrong_mode / "compose.yaml").chmod(0o700)
        sources["v2-mode-mismatch"] = wrong_mode

        empty_directory = self._v2_release("empty-directory")
        (empty_directory / "scripts/empty").mkdir(mode=0o700)
        sources["v2-empty-directory"] = empty_directory

        mixed = self._v2_release("mixed-profile")
        (mixed / host_state.RUNTIME_MANIFEST).write_bytes(
            self._manifest_bytes({"compose.yaml": 0o600})
        )
        (mixed / host_state.RUNTIME_MANIFEST).chmod(0o600)
        sources["v2-legacy-mixed-profile"] = mixed

        symlink = self._v2_release("symlink")
        (symlink / "compose.yaml").unlink()
        os.symlink("infra/nginx/nginx.conf", symlink / "compose.yaml")
        sources["v2-symlink"] = symlink

        hardlink = self._v2_release("hardlink")
        (hardlink / "scripts/backup_tools/offsite_backup.py").unlink()
        os.link(
            hardlink / "compose.yaml",
            hardlink / "scripts/backup_tools/offsite_backup.py",
        )
        sources["v2-hardlink"] = hardlink

        fifo = self._v2_release("fifo")
        (fifo / "compose.yaml").unlink()
        os.mkfifo(fifo / "compose.yaml", 0o600)
        sources["v2-fifo"] = fifo

        socket_entry = self._v2_release("socket")
        (socket_entry / "compose.yaml").unlink()
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            unix_socket.bind(str(socket_entry / "compose.yaml"))
        finally:
            unix_socket.close()
        sources["v2-socket"] = socket_entry

        oversize = self._v2_release("oversize")
        with (oversize / "compose.yaml").open("wb") as output:
            output.truncate(host_state.MAX_RELEASE_FILE_SIZE + 1)
        (oversize / "compose.yaml").chmod(0o600)
        sources["v2-oversize"] = oversize

        private_key = self._v2_release("private-key")
        (private_key / "compose.yaml").write_bytes(
            b"-----BEGIN PRIVATE KEY-----\nsynthetic\n"
        )
        (private_key / "compose.yaml").chmod(0o600)
        sources["v2-private-key-marker"] = private_key

        manifest_symlink = self._v2_release("manifest-symlink")
        (manifest_symlink / host_state.RUNTIME_MANIFEST).unlink()
        os.symlink("compose.yaml", manifest_symlink / host_state.RUNTIME_MANIFEST)
        sources["v2-manifest-symlink"] = manifest_symlink

        manifest_mode = self._v2_release("manifest-mode")
        (manifest_mode / host_state.RUNTIME_MANIFEST).chmod(0o700)
        sources["v2-manifest-mode"] = manifest_mode

        invalid_manifest = self._v2_release("invalid-manifest")
        (invalid_manifest / host_state.RUNTIME_MANIFEST).write_bytes(b"{}\n")
        (invalid_manifest / host_state.RUNTIME_MANIFEST).chmod(0o600)
        sources["v2-invalid-manifest"] = invalid_manifest

        oversized_manifest = self._v2_release("oversized-manifest")
        (oversized_manifest / host_state.RUNTIME_MANIFEST).write_bytes(
            b" " * (host_state.MAX_RUNTIME_MANIFEST_SIZE + 1)
        )
        (oversized_manifest / host_state.RUNTIME_MANIFEST).chmod(0o600)
        sources["v2-oversized-manifest"] = oversized_manifest
        return sources

    def _legacy_release(self, name: str) -> Path:
        return self._release_root(
            name,
            host_state.LEGACY_RELEASE_FILES,
            prefix="legacy",
            manifest=False,
        )

    def _v2_release(self, name: str) -> Path:
        return self._release_root(name, V2_FILES, prefix="v2", manifest=True)

    def _release_root(
        self,
        name: str,
        files: Mapping[str, int],
        *,
        prefix: str,
        manifest: bool,
    ) -> Path:
        root = self.temp / name
        root.mkdir(mode=0o700)
        directories = {
            str(parent)
            for relative in files
            for parent in PurePosixPath(relative).parents
            if str(parent) != "."
        }
        for relative in sorted(directories, key=lambda value: value.count("/")):
            (root / relative).mkdir(mode=0o700)
        if manifest:
            manifest_path = root / host_state.RUNTIME_MANIFEST
            manifest_path.write_bytes(self._manifest_bytes(files))
            manifest_path.chmod(0o600)
        for relative, mode in files.items():
            target = root / relative
            target.write_text(f"{prefix}:{relative}\n", encoding="utf-8")
            target.chmod(mode)
        return root

    def _stage(
        self,
        lock: host_state.OperationLock,
        source: Path,
        digest: str,
        revision: str,
    ) -> host_state.ReleaseIdentity:
        return host_state.stage_release(
            self.paths,
            lock,
            source,
            application_revision=revision,
            runtime_config_digest=digest,
            runtime_config_revision=revision,
        )

    @staticmethod
    def _manifest_bytes(files: Mapping[str, int]) -> bytes:
        return RuntimeConfigEvolutionTest._json_bytes(
            {
                "formatVersion": 2,
                "project": "our-ledger",
                "files": [
                    {"path": relative, "mode": f"{mode:04o}"}
                    for relative, mode in sorted(files.items())
                ],
            }
        )

    @staticmethod
    def _manifest_with_entry(path: object, mode: object, **extra: object) -> bytes:
        entry = {"path": path, "mode": mode, **extra}
        return RuntimeConfigEvolutionTest._json_bytes(
            {
                "formatVersion": 2,
                "project": "our-ledger",
                "files": [entry],
            }
        )

    @staticmethod
    def _json_bytes(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"

    @staticmethod
    def _tree_fingerprint(root: Path) -> list[tuple[str, str, int, bytes | str]]:
        result = []
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            path_stat = os.lstat(path)
            mode = stat.S_IMODE(path_stat.st_mode)
            if stat.S_ISDIR(path_stat.st_mode):
                result.append((relative, "directory", mode, b""))
            elif stat.S_ISLNK(path_stat.st_mode):
                result.append((relative, "symlink", mode, os.readlink(path)))
            elif stat.S_ISREG(path_stat.st_mode):
                result.append((relative, "file", mode, path.read_bytes()))
            else:
                result.append((relative, "other", mode, b""))
        return result

    @staticmethod
    def _write_archive(
        source: Path,
        archive: Path,
        *,
        omit: set[str] | None = None,
        extra_file: str | None = None,
        extra_directory: str | None = None,
        duplicate: str | None = None,
        mode_override: dict[str, int] | None = None,
        type_override: dict[str, bytes] | None = None,
        size_override: dict[str, int] | None = None,
        payload_override: dict[str, bytes] | None = None,
    ) -> None:
        omit = omit or set()
        mode_override = mode_override or {}
        type_override = type_override or {}
        size_override = size_override or {}
        payload_override = payload_override or {}
        profile = host_state._validate_release(source)
        with tarfile.open(archive, "w") as bundle:
            root_member = tarfile.TarInfo("runtime")
            root_member.type = tarfile.DIRTYPE
            root_member.mode = 0o755
            bundle.addfile(root_member)
            for relative in sorted(profile.directories, key=lambda value: value.count("/")):
                member = tarfile.TarInfo(f"runtime/{relative}")
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                bundle.addfile(member)
            if extra_directory is not None:
                member = tarfile.TarInfo(f"runtime/{extra_directory}")
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                bundle.addfile(member)
            for relative, mode in profile.all_file_modes.items():
                if relative in omit:
                    continue
                payload = payload_override.get(relative, (source / relative).read_bytes())
                member = tarfile.TarInfo(f"runtime/{relative}")
                member.mode = mode_override.get(relative, mode)
                member.type = type_override.get(relative, tarfile.REGTYPE)
                member.size = size_override.get(relative, len(payload))
                if member.type == tarfile.SYMTYPE:
                    member.linkname = "/tmp/outside"
                    member.size = 0
                    bundle.addfile(member)
                elif member.type == tarfile.LNKTYPE:
                    member.linkname = "runtime/infra/nginx/nginx.conf"
                    member.size = 0
                    bundle.addfile(member)
                elif member.type != tarfile.REGTYPE:
                    member.size = 0
                    bundle.addfile(member)
                else:
                    content = payload
                    if member.size > len(content):
                        content += b"x" * (member.size - len(content))
                    bundle.addfile(member, io.BytesIO(content))
                if duplicate == relative:
                    duplicate_member = tarfile.TarInfo(f"runtime/{relative}")
                    duplicate_member.mode = mode
                    duplicate_member.size = len(payload)
                    bundle.addfile(duplicate_member, io.BytesIO(payload))
            if extra_file is not None:
                payload = b"extra\n"
                member = tarfile.TarInfo(f"runtime/{extra_file}")
                member.mode = 0o600
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))


if __name__ == "__main__":
    unittest.main()
