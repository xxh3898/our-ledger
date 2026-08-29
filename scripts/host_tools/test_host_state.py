from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.host_tools import host_state, production_host


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "backup-production.sh"
FULL_CI = ROOT / ".github" / "workflows" / "full-ci.yml"
RUNTIME_DOCKERFILE = ROOT / "runtime-config.Dockerfile"
DETECTOR = ROOT / "scripts" / "detect-runtime-config-change.sh"
REVISION_ONE = "1" * 40
REVISION_TWO = "2" * 40
DIGEST_ONE = "sha256:" + ("a" * 64)
DIGEST_TWO = "sha256:" + ("b" * 64)


class HostStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary.name).resolve()
        self.paths = host_state.HostPaths(self.temp / "host")
        host_state.initialize_layout(self.paths)
        self.source = self._release_source("one")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_fresh_layout_is_owner_only_and_inspects_fresh(self) -> None:
        for directory in (
            self.paths.app_root,
            self.paths.runtime_root,
            self.paths.releases,
            self.paths.state_dir,
            self.paths.pending_dir,
            self.paths.operations,
        ):
            self.assertEqual(stat.S_IMODE(os.lstat(directory).st_mode), 0o700)

        with host_state.OperationLock(self.paths) as lock:
            result = host_state.inspect_state(self.paths, lock)

        self.assertEqual(result["status"], "FRESH")
        self.assertFalse(result["pending"])
        self.assertFalse(os.path.lexists(self.paths.lock))

    def test_second_holder_fails_immediately_without_stealing_lock(self) -> None:
        with host_state.OperationLock(self.paths) as deploy_lock:
            lock_stat = os.lstat(self.paths.lock)
            with self.assertRaises(host_state.LockBusyError):
                with host_state.OperationLock(self.paths):
                    self.fail("second holder acquired the lock")
            self.assertEqual(os.lstat(self.paths.lock).st_ino, lock_stat.st_ino)

    def test_stale_and_symlink_locks_fail_closed(self) -> None:
        os.mkdir(self.paths.lock, 0o700)
        with self.assertRaises(host_state.LockBusyError):
            with host_state.OperationLock(self.paths):
                pass
        os.rmdir(self.paths.lock)
        os.symlink(self.paths.state_dir, self.paths.lock)
        with self.assertRaises(host_state.ContractError):
            with host_state.OperationLock(self.paths):
                pass

    def test_lock_tamper_is_not_broadly_removed(self) -> None:
        with self.assertRaises(host_state.ContractError):
            with host_state.OperationLock(self.paths):
                (self.paths.lock / "unexpected").write_text("x", encoding="utf-8")

        self.assertTrue(self.paths.lock.is_dir())
        self.assertTrue((self.paths.lock / "unexpected").is_file())

    def test_stage_uses_digest_path_and_is_idempotent(self) -> None:
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
            reused = self._stage(lock)

        expected = self.paths.releases / ("a" * 64)
        self.assertEqual(identity, reused)
        self.assertTrue(expected.is_dir())
        self.assertEqual(identity.release_name, expected.name)
        self.assertEqual(
            identity.runtime_config_content_sha256,
            host_state.release_content_sha256(expected),
        )

    def test_repository_runtime_sources_form_one_verified_release(self) -> None:
        source = self.temp / "repository-release"
        source.mkdir(mode=0o700)
        for relative in sorted(
            host_state.RELEASE_DIRECTORIES,
            key=lambda item: item.count("/"),
        ):
            (source / relative).mkdir(mode=0o700)
        for relative, mode in host_state.RELEASE_FILES.items():
            repository_relative = "compose.prod.yaml" if relative == "compose.yaml" else relative
            shutil.copyfile(ROOT / repository_relative, source / relative)
            (source / relative).chmod(mode)

        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock, source=source)

        release = self.paths.releases / identity.release_name
        self.assertEqual(
            (release / "scripts/backup-production.sh").read_bytes(),
            WRAPPER.read_bytes(),
        )
        self.assertEqual(
            stat.S_IMODE((release / "scripts/backup_tools/backup_core.sh").stat().st_mode),
            0o600,
        )

    def test_same_digest_different_content_is_never_overwritten(self) -> None:
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
        release = self.paths.releases / identity.release_name
        before = self._tree_fingerprint(release)
        changed = self._release_source("different")

        with host_state.OperationLock(self.paths) as lock:
            with self.assertRaises(host_state.ContractError):
                self._stage(lock, source=changed)

        self.assertEqual(self._tree_fingerprint(release), before)

    def test_source_allowlist_symlink_hardlink_and_fifo_fail_closed(self) -> None:
        cases = []

        unexpected = self._release_source("unexpected")
        extra = unexpected / "token"
        extra.write_text("not-a-token", encoding="utf-8")
        extra.chmod(0o600)
        cases.append(unexpected)

        symlink = self._release_source("symlink")
        target = symlink / "compose.yaml"
        target.unlink()
        os.symlink("infra/nginx/nginx.conf", target)
        cases.append(symlink)

        hardlink = self._release_source("hardlink")
        original = hardlink / "compose.yaml"
        linked = self.temp / "hardlink-copy"
        os.link(original, linked)
        cases.append(hardlink)

        fifo = self._release_source("fifo")
        fifo_target = fifo / "compose.yaml"
        fifo_target.unlink()
        os.mkfifo(fifo_target, 0o600)
        cases.append(fifo)

        for source in cases:
            with self.subTest(source=source.name):
                with host_state.OperationLock(self.paths) as lock:
                    with self.assertRaises(host_state.ContractError):
                        self._stage(lock, source=source)
                self.assertEqual(list(self.paths.releases.iterdir()), [])

    def test_source_root_symlink_and_host_ancestor_cannot_escape(self) -> None:
        linked_source = self.temp / "linked-source"
        os.symlink(self.source, linked_source)

        for source in (linked_source, self.paths.app_root, Path("relative-source")):
            with self.subTest(source=source):
                with host_state.OperationLock(self.paths) as lock:
                    with self.assertRaises(host_state.ContractError):
                        self._stage(lock, source=source)

        real_parent = self.temp / "real-parent"
        real_parent.mkdir(mode=0o700)
        linked_parent = self.temp / "linked-parent"
        os.symlink(real_parent, linked_parent)
        escaped_paths = host_state.HostPaths(linked_parent / "host")
        with self.assertRaises(host_state.ContractError):
            host_state.initialize_layout(escaped_paths)
        self.assertFalse((real_parent / "host").exists())

        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
            with self.assertRaises(host_state.ContractError):
                self._stage(
                    lock,
                    source=self.paths.releases / identity.release_name,
                    digest=DIGEST_TWO,
                    application_revision=REVISION_TWO,
                    runtime_revision=REVISION_TWO,
                )

    def test_private_key_material_and_oversized_file_fail_closed(self) -> None:
        private = self._release_source("private")
        (private / "compose.yaml").write_text(
            "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n",
            encoding="utf-8",
        )
        (private / "compose.yaml").chmod(0o600)

        oversized = self._release_source("oversized")
        with (oversized / "compose.yaml").open("wb") as target:
            target.truncate(host_state.MAX_RELEASE_FILE_SIZE + 1)
        (oversized / "compose.yaml").chmod(0o600)

        for source in (private, oversized):
            with self.subTest(source=source.name):
                with host_state.OperationLock(self.paths) as lock:
                    with self.assertRaises(host_state.ContractError):
                        self._stage(lock, source=source)

    def test_pending_blocks_new_stage_and_transaction(self) -> None:
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
            host_state.begin_pending(self.paths, lock, identity)
            with self.assertRaises(host_state.ContractError):
                self._stage(lock)
            with self.assertRaises(host_state.ContractError):
                host_state.begin_pending(self.paths, lock, identity)

        self.assertTrue(self.paths.pending_file.is_file())
        self.assertEqual(stat.S_IMODE(self.paths.pending_file.stat().st_mode), 0o600)

    def test_commit_updates_relative_current_and_versioned_state(self) -> None:
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
            host_state.begin_pending(self.paths, lock, identity)
            committed = host_state.commit_pending(self.paths, lock)
            result = host_state.inspect_state(self.paths, lock)

        self.assertEqual(committed, identity)
        self.assertEqual(os.readlink(self.paths.current), f"releases/{identity.release_name}")
        self.assertEqual(result["status"], "READY")
        self.assertFalse(result["pending"])
        state = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["formatVersion"], 1)
        self.assertEqual(state["project"], "our-ledger")
        self.assertFalse(os.path.lexists(self.paths.pending_file))
        self.assertEqual(stat.S_IMODE(self.paths.state_file.stat().st_mode), 0o600)
        self.assertEqual(list(self.paths.state_dir.glob("*.tmp")), [])

    def test_crash_after_current_preserves_pending_for_explicit_recovery(self) -> None:
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
            host_state.begin_pending(self.paths, lock, identity)
            with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
                host_state.commit_pending(
                    self.paths,
                    lock,
                    after_current=lambda: (_ for _ in ()).throw(
                        RuntimeError("synthetic crash")
                    ),
                )

        with host_state.OperationLock(self.paths) as lock:
            result = host_state.inspect_state(self.paths, lock)
            with self.assertRaises(host_state.ContractError):
                host_state.clear_abandoned_pending(self.paths, lock)

        self.assertEqual(result["status"], "PENDING")
        self.assertTrue(self.paths.pending_file.is_file())

    def test_semantically_inconsistent_pending_fails_closed(self) -> None:
        second_source = self._release_source("pending-two")
        with host_state.OperationLock(self.paths) as lock:
            first = self._stage(lock)
            host_state.begin_pending(self.paths, lock, first)
            host_state.commit_pending(self.paths, lock)
            second = self._stage(
                lock,
                source=second_source,
                digest=DIGEST_TWO,
                application_revision=REVISION_TWO,
                runtime_revision=REVISION_TWO,
            )
            host_state.begin_pending(self.paths, lock, second)

        pending = json.loads(self.paths.pending_file.read_text(encoding="utf-8"))
        pending["previous"] = None
        self.paths.pending_file.write_text(
            json.dumps(pending, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.paths.pending_file.chmod(0o600)

        with host_state.OperationLock(self.paths) as lock:
            with self.assertRaises(host_state.ContractError):
                host_state.inspect_state(self.paths, lock)

        self.assertTrue(self.paths.pending_file.is_file())

    def test_abandoned_pending_clear_is_limited_to_unchanged_previous_state(self) -> None:
        with host_state.OperationLock(self.paths) as lock:
            identity = self._stage(lock)
            host_state.begin_pending(self.paths, lock, identity)
            host_state.clear_abandoned_pending(self.paths, lock)

        self.assertFalse(os.path.lexists(self.paths.pending_file))
        self.assertTrue((self.paths.releases / identity.release_name).is_dir())

    def test_second_commit_preserves_exact_previous_identity(self) -> None:
        second_source = self._release_source("two")
        with host_state.OperationLock(self.paths) as lock:
            first = self._stage(lock)
            host_state.begin_pending(self.paths, lock, first)
            host_state.commit_pending(self.paths, lock)
            second = self._stage(
                lock,
                source=second_source,
                digest=DIGEST_TWO,
                application_revision=REVISION_TWO,
                runtime_revision=REVISION_TWO,
            )
            host_state.begin_pending(self.paths, lock, second)
            host_state.commit_pending(self.paths, lock)

        state = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["current"], second.to_json())
        self.assertEqual(state["previous"], first.to_json())
        self.assertEqual(os.readlink(self.paths.current), f"releases/{second.release_name}")

    def test_corrupt_or_symlink_state_pending_and_current_fail_closed(self) -> None:
        corrupt_cases = (
            self.paths.state_file,
            self.paths.pending_file,
        )
        for target in corrupt_cases:
            with self.subTest(target=target.name):
                target.write_text('{"formatVersion":1}\n', encoding="utf-8")
                target.chmod(0o600)
                with host_state.OperationLock(self.paths) as lock:
                    with self.assertRaises(host_state.ContractError):
                        host_state.inspect_state(self.paths, lock)
                target.unlink()

                os.symlink(self.source / "compose.yaml", target)
                with self.assertRaises(host_state.ContractError):
                    host_state.validate_layout(self.paths)
                target.unlink()

        os.symlink("../../outside", self.paths.current)
        with self.assertRaises(host_state.ContractError):
            host_state.validate_layout(self.paths)

    def test_boolean_format_version_fails_closed(self) -> None:
        second_source = self._release_source("boolean-version-two")
        with host_state.OperationLock(self.paths) as lock:
            first = self._stage(lock)
            host_state.begin_pending(self.paths, lock, first)
            host_state.commit_pending(self.paths, lock)

        state = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        state["formatVersion"] = True
        self.paths.state_file.write_text(
            json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.paths.state_file.chmod(0o600)
        with host_state.OperationLock(self.paths) as lock:
            with self.assertRaises(host_state.ContractError):
                host_state.inspect_state(self.paths, lock)

        state["formatVersion"] = host_state.FORMAT_VERSION
        self.paths.state_file.write_text(
            json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.paths.state_file.chmod(0o600)
        with host_state.OperationLock(self.paths) as lock:
            second = self._stage(
                lock,
                source=second_source,
                digest=DIGEST_TWO,
                application_revision=REVISION_TWO,
                runtime_revision=REVISION_TWO,
            )
            host_state.begin_pending(self.paths, lock, second)

        pending = json.loads(self.paths.pending_file.read_text(encoding="utf-8"))
        pending["formatVersion"] = True
        self.paths.pending_file.write_text(
            json.dumps(pending, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.paths.pending_file.chmod(0o600)
        with host_state.OperationLock(self.paths) as lock:
            with self.assertRaises(host_state.ContractError):
                host_state.inspect_state(self.paths, lock)

    def test_partial_stage_requires_explicit_safe_cleanup(self) -> None:
        stage_name = ".stage-" + ("c" * 32)
        stage = self.paths.releases / stage_name
        stage.mkdir(mode=0o700)
        (stage / "infra").mkdir(mode=0o700)

        with host_state.OperationLock(self.paths) as lock:
            result = host_state.inspect_state(self.paths, lock)
            with self.assertRaises(host_state.ContractError):
                self._stage(lock)
            host_state.clear_abandoned_stage(self.paths, lock, stage_name)

        self.assertEqual(result["abandonedStages"], [stage_name])
        self.assertFalse(os.path.lexists(stage))

    def test_stage_and_state_mutations_require_matching_held_lock(self) -> None:
        unheld = host_state.OperationLock(self.paths)
        with self.assertRaises(host_state.ContractError):
            host_state.stage_release(
                self.paths,
                unheld,
                self.source,
                application_revision=REVISION_ONE,
                runtime_config_digest=DIGEST_ONE,
                runtime_config_revision=REVISION_ONE,
            )

        other_paths = host_state.HostPaths(self.temp / "other-host")
        host_state.initialize_layout(other_paths)
        with host_state.OperationLock(self.paths) as lock:
            with self.assertRaises(host_state.ContractError):
                host_state.inspect_state(other_paths, lock)

    def test_standalone_backup_and_deploy_share_one_lock(self) -> None:
        runner_calls: list[list[str]] = []

        def runner(arguments):
            self.assertTrue(self.paths.lock.is_dir())
            runner_calls.append(list(arguments))
            return 0

        with self.assertRaises(host_state.ContractError):
            production_host.run_backup_core(
                ["--project-name", "synthetic"],
                paths=self.paths,
                lock=host_state.OperationLock(self.paths),
                runner=runner,
            )

        result = production_host.run_standalone_backup(
            ["--project-name", "synthetic"],
            paths=self.paths,
            runner=runner,
        )
        self.assertEqual(result, 0)
        self.assertEqual(len(runner_calls), 1)

        with host_state.OperationLock(self.paths) as deploy_lock:
            with self.assertRaises(host_state.LockBusyError):
                production_host.run_standalone_backup(
                    ["--project-name", "synthetic"],
                    paths=self.paths,
                    runner=runner,
                )
            direct_result = production_host.run_backup_core(
                ["--project-name", "synthetic"],
                paths=self.paths,
                lock=deploy_lock,
                runner=runner,
            )

        self.assertEqual(direct_result, 0)
        self.assertEqual(len(runner_calls), 2)

    def test_public_backup_has_no_lock_bypass_or_host_root_override(self) -> None:
        wrapper = WRAPPER.read_text(encoding="utf-8")
        worker = (ROOT / "scripts/host_tools/production_host.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("scripts.host_tools.production_host backup", wrapper)
        self.assertNotIn("skip-lock", wrapper + worker)
        self.assertNotIn("--app-root", worker)
        self.assertNotIn("--root", worker)
        self.assertNotIn("OUR_LEDGER_", worker)
        self.assertIn(str(host_state.PRODUCTION_APP_ROOT), (ROOT / "scripts/host_tools/host_state.py").read_text(encoding="utf-8"))
        self.assertNotIn("synthetic_host.py", RUNTIME_DOCKERFILE.read_text(encoding="utf-8"))
        self.assertNotIn("synthetic_host.py", DETECTOR.read_text(encoding="utf-8"))

        result = subprocess.run(
            [
                "python3",
                "-B",
                "-m",
                "scripts.host_tools.production_host",
                "backup",
                "--root",
                str(self.paths.app_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)

    def test_host_state_gate_is_wired_to_local_and_hosted_full_ci(self) -> None:
        local_gate = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
        hosted_gate = FULL_CI.read_text(encoding="utf-8")

        self.assertEqual(local_gate.count("verify-host-state.sh"), 1)
        self.assertIn("  host-state:\n", hosted_gate)
        self.assertEqual(hosted_gate.count("run: ./scripts/verify-host-state.sh"), 1)

    def test_synthetic_adapter_uses_only_injected_temp_root(self) -> None:
        injected = self.temp / "injected-host"
        result = subprocess.run(
            [
                "python3",
                "-B",
                "-m",
                "scripts.host_tools.synthetic_host",
                "--app-root",
                str(injected),
                "inspect",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "FRESH")
        self.assertTrue((injected / "runtime-config").is_dir())
        self.assertNotIn(str(host_state.PRODUCTION_APP_ROOT), result.stdout + result.stderr)

    def test_identity_rejects_uppercase_or_path_like_values(self) -> None:
        invalid = (
            ("0" * 40, DIGEST_ONE, REVISION_ONE),
            ("A" * 40, DIGEST_ONE, REVISION_ONE),
            (REVISION_ONE, "sha256:../outside", REVISION_ONE),
            (REVISION_ONE, "sha256:" + ("0" * 64), REVISION_ONE),
            (REVISION_ONE, "sha256:" + ("A" * 64), REVISION_ONE),
            (REVISION_ONE, DIGEST_ONE, "2" * 39),
        )
        for application, digest, runtime in invalid:
            with self.subTest(digest=digest):
                with self.assertRaises(host_state.ContractError):
                    host_state.ReleaseIdentity(
                        application,
                        digest,
                        runtime,
                        "c" * 64,
                    )

    def _stage(
        self,
        lock: host_state.OperationLock,
        *,
        source: Path | None = None,
        digest: str = DIGEST_ONE,
        application_revision: str = REVISION_ONE,
        runtime_revision: str = REVISION_ONE,
    ) -> host_state.ReleaseIdentity:
        return host_state.stage_release(
            self.paths,
            lock,
            source if source is not None else self.source,
            application_revision=application_revision,
            runtime_config_digest=digest,
            runtime_config_revision=runtime_revision,
        )

    def _release_source(self, suffix: str) -> Path:
        source = self.temp / f"source-{suffix}"
        source.mkdir(mode=0o700)
        for relative in sorted(
            host_state.RELEASE_DIRECTORIES,
            key=lambda item: item.count("/"),
        ):
            (source / relative).mkdir(mode=0o700)
        for relative, mode in host_state.RELEASE_FILES.items():
            target = source / relative
            target.write_text(f"{relative}:{suffix}\n", encoding="utf-8")
            target.chmod(mode)
        return source

    @staticmethod
    def _tree_fingerprint(root: Path) -> list[tuple[str, int, bytes]]:
        result = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            result.append(
                (
                    path.relative_to(root).as_posix(),
                    stat.S_IMODE(path.stat().st_mode),
                    path.read_bytes(),
                )
            )
        return result


if __name__ == "__main__":
    unittest.main()
