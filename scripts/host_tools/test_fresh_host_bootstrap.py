from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.host_tools import fresh_bootstrap_state, host_state
from scripts.host_tools.fresh_host_bootstrap import (
    FreshBootstrapError,
    FreshBootstrapInterventionRequired,
    FreshCandidateArtifacts,
    read_token,
    run_fresh_bootstrap,
)
from scripts.host_tools.host_state import HostPaths, OperationLock, SchemaAuthority


ROOT = Path(__file__).resolve().parents[2]
REVISION = "1" * 40
OTHER_REVISION = "2" * 40
DIGEST = "sha256:" + ("c" * 64)
OTHER_DIGEST = "sha256:" + ("d" * 64)
COMMAND = f"bootstrap-our-ledger-v1 {REVISION} {DIGEST} release_actor"
SCHEMA = SchemaAuthority("8", 0, "e" * 64)
MARKER = "f" * 64


class FakeFreshAdapter:
    def __init__(self, source: Path):
        self.source = source
        self.calls: list[str] = []
        self.resources_exist = False
        self.postgres_ready = False
        self.schema: SchemaAuthority | None = None
        self.household_created = False
        self.household_exact = False
        self.application_ready = False
        self.marker: str | None = None
        self.input_exists = True
        self.persisted = False
        self.invalid_backup = False
        self.initial_verified = False
        self.migration_schema = SCHEMA
        self.household_result: str | None = None
        self.household_exact_after_run = True
        self.artifact_digest = DIGEST

    def validate_authority(self) -> None:
        self.calls.append("validate-authority")

    def validate_resource_authority(self, *, recovering: bool) -> None:
        self.calls.append(f"validate-resources:{recovering}")
        if self.resources_exist and not recovering:
            raise FreshBootstrapError("unexpected resources")

    def prepare_artifacts(self, request, token: bytearray) -> FreshCandidateArtifacts:
        self.calls.append("prepare-artifacts")
        return FreshCandidateArtifacts(
            revision=request.revision,
            api_reference=f"ghcr.io/xxh3898/our-ledger-api:{request.revision}",
            web_reference=f"ghcr.io/xxh3898/our-ledger-web:{request.revision}",
            runtime_config_digest=self.artifact_digest,
            runtime_config_revision=request.revision,
            runtime_source=self.source,
        )

    def start_postgres(self, candidate) -> None:
        self.calls.append("start-postgres")
        self.resources_exist = True
        self.postgres_ready = True

    def postgres_is_ready(self, candidate) -> bool:
        self.calls.append("postgres-ready")
        return self.postgres_ready

    def run_migration(self, candidate) -> None:
        self.calls.append("migration")
        self.schema = self.migration_schema

    def read_schema_authority(self) -> SchemaAuthority:
        self.calls.append("schema")
        if self.schema is None:
            raise FreshBootstrapError("schema unavailable")
        return self.schema

    def run_household_bootstrap(self, candidate) -> str:
        self.calls.append("household-bootstrap")
        if self.household_result is not None:
            self.household_created = self.household_result in {"created", "verified"}
            self.household_exact = self.household_exact_after_run
            return self.household_result
        if self.initial_verified or self.household_created:
            self.household_created = True
            self.household_exact = True
            return "verified"
        self.household_created = True
        self.household_exact = True
        return "created"

    def household_bootstrap_is_exact(self) -> bool:
        self.calls.append("household-exact")
        return self.household_exact

    def start_application(self, candidate) -> None:
        self.calls.append("start-application")
        self.application_ready = True

    def candidate_is_ready(self, candidate) -> bool:
        self.calls.append("candidate-ready")
        return self.application_ready

    def run_verified_backup(self, lock: OperationLock) -> str:
        self.calls.append("backup")
        self.marker = MARKER
        return MARKER

    def backup_marker_is_verified(self, marker_sha256: str) -> bool:
        self.calls.append("backup-verified")
        return not self.invalid_backup and self.marker == marker_sha256

    def consume_bootstrap_input(self) -> None:
        self.calls.append("consume-input")
        self.input_exists = False

    def bootstrap_input_exists(self) -> bool:
        self.calls.append("input-exists")
        return self.input_exists

    def persist_candidate_images(self, candidate) -> None:
        self.calls.append("persist-images")
        self.persisted = True

    def cleanup(self) -> None:
        self.calls.append("cleanup")


class FreshHostBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary.name).resolve()
        self.paths = HostPaths(self.temp / "host")
        host_state.initialize_layout(self.paths)
        self.source = self._release_source()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_full_fresh_transaction_commits_existing_b2_compatible_state(self) -> None:
        adapter = FakeFreshAdapter(self.source)
        token = read_token(b"synthetic-token\n")

        result = self._run(adapter, token)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(token, bytearray())
        self.assertFalse(adapter.input_exists)
        self.assertTrue(adapter.persisted)
        self.assertFalse(os.path.lexists(self.paths.pending_file))
        state = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertIsNone(state["previous"])
        self.assertEqual(state["current"]["applicationRevision"], REVISION)
        with OperationLock(self.paths) as lock:
            inspected = host_state.inspect_state(self.paths, lock)
        self.assertEqual(inspected["status"], "READY")
        self.assertFalse(inspected["pending"])

    def test_all_durable_phase_crashes_resume_with_same_identity(self) -> None:
        phases = fresh_bootstrap_state.FRESH_PHASES
        for phase in phases:
            with self.subTest(phase=phase):
                paths = HostPaths(self.temp / f"host-{phase.lower()}")
                host_state.initialize_layout(paths)
                source = self._release_source(phase.lower())
                adapter = FakeFreshAdapter(source)
                crashed = False

                def crash_hook(observed: str) -> None:
                    nonlocal crashed
                    if observed == phase and not crashed:
                        crashed = True
                        raise RuntimeError("synthetic crash")

                with self.assertRaises(FreshBootstrapError):
                    run_fresh_bootstrap(
                        COMMAND,
                        read_token(b"token\n"),
                        paths=paths,
                        adapter=adapter,
                        clock=lambda: "2026-08-30T00:00:00Z",
                        crash_hook=crash_hook,
                    )
                self.assertTrue(paths.pending_file.is_file())

                result = run_fresh_bootstrap(
                    COMMAND,
                    read_token(b"token\n"),
                    paths=paths,
                    adapter=adapter,
                    clock=lambda: "2026-08-30T00:00:01Z",
                )
                self.assertEqual(result.status, "SUCCESS")
                with OperationLock(paths) as lock:
                    self.assertEqual(host_state.inspect_state(paths, lock)["status"], "READY")

    def test_commit_recovers_crash_after_current_and_after_state(self) -> None:
        for boundary in ("current", "state"):
            with self.subTest(boundary=boundary):
                paths = HostPaths(self.temp / f"commit-{boundary}")
                host_state.initialize_layout(paths)
                source = self._release_source(f"commit-{boundary}")
                with OperationLock(paths) as lock:
                    candidate = host_state.stage_release(
                        paths,
                        lock,
                        source,
                        application_revision=REVISION,
                        runtime_config_digest=DIGEST,
                        runtime_config_revision=REVISION,
                    )
                    fresh_bootstrap_state.begin(
                        paths,
                        lock,
                        candidate,
                        actor="actor",
                        started_at="2026-08-30T00:00:00Z",
                    )
                    self._advance_to_input_consumed(paths, lock)
                    callback = lambda: (_ for _ in ()).throw(RuntimeError("crash"))
                    with self.assertRaises(RuntimeError):
                        fresh_bootstrap_state.commit(
                            paths,
                            lock,
                            after_current=callback if boundary == "current" else None,
                            after_state=callback if boundary == "state" else None,
                        )

                with OperationLock(paths) as lock:
                    fresh_bootstrap_state.commit(paths, lock)
                    self.assertEqual(host_state.inspect_state(paths, lock)["status"], "READY")

    def test_normal_and_fresh_pending_cannot_cross_consume(self) -> None:
        with OperationLock(self.paths) as lock:
            candidate = self._stage(lock)
            host_state.begin_deployment_pending(
                self.paths,
                lock,
                candidate,
                actor="actor",
                started_at="2026-08-30T00:00:00Z",
            )
            with self.assertRaises(host_state.ContractError):
                fresh_bootstrap_state.inspect(self.paths, lock)

        other = HostPaths(self.temp / "fresh-pending")
        host_state.initialize_layout(other)
        source = self._release_source("fresh-pending")
        with OperationLock(other) as lock:
            candidate = host_state.stage_release(
                other,
                lock,
                source,
                application_revision=REVISION,
                runtime_config_digest=DIGEST,
                runtime_config_revision=REVISION,
            )
            fresh_bootstrap_state.begin(
                other,
                lock,
                candidate,
                actor="actor",
                started_at="2026-08-30T00:00:00Z",
            )
            with self.assertRaises(host_state.ContractError):
                host_state.inspect_state(other, lock)

    def test_existing_current_blocks_rerun_before_artifact_or_resource_mutation(self) -> None:
        adapter = FakeFreshAdapter(self.source)
        self._run(adapter, read_token(b"token\n"))
        before = self._tree_fingerprint(self.paths.app_root)
        retry = FakeFreshAdapter(self.source)

        with self.assertRaises(FreshBootstrapError):
            self._run(retry, read_token(b"token\n"))

        self.assertNotIn("prepare-artifacts", retry.calls)
        self.assertNotIn("start-postgres", retry.calls)
        self.assertEqual(self._tree_fingerprint(self.paths.app_root), before)

    def test_initial_verified_household_state_requires_intervention(self) -> None:
        adapter = FakeFreshAdapter(self.source)
        adapter.initial_verified = True
        adapter.household_created = True
        adapter.household_exact = True

        with self.assertRaises(FreshBootstrapInterventionRequired):
            self._run(adapter, read_token(b"token\n"))

        with OperationLock(self.paths) as lock:
            pending = fresh_bootstrap_state.read(self.paths, lock, required=True)
        self.assertEqual(pending["phase"], "BOOTSTRAP_STARTED")
        self.assertFalse(os.path.lexists(self.paths.current))

    def test_ambiguous_schema_and_household_state_require_intervention(self) -> None:
        schema_adapter = FakeFreshAdapter(self.source)
        schema_adapter.migration_schema = SchemaAuthority("7", 0, "7" * 64)

        with self.assertRaises(FreshBootstrapInterventionRequired):
            self._run(schema_adapter, read_token(b"token\n"))

        with OperationLock(self.paths) as lock:
            pending = fresh_bootstrap_state.read(self.paths, lock, required=True)
        self.assertEqual(pending["phase"], "MIGRATION_STARTED")
        self.assertFalse(os.path.lexists(self.paths.current))

        household_paths = HostPaths(self.temp / "ambiguous-household")
        host_state.initialize_layout(household_paths)
        household_adapter = FakeFreshAdapter(
            self._release_source("ambiguous-household")
        )
        household_adapter.household_result = "created"
        household_adapter.household_exact_after_run = False

        with self.assertRaises(FreshBootstrapInterventionRequired):
            run_fresh_bootstrap(
                COMMAND,
                read_token(b"token\n"),
                paths=household_paths,
                adapter=household_adapter,
                clock=lambda: "2026-08-30T00:00:00Z",
            )

        with OperationLock(household_paths) as lock:
            pending = fresh_bootstrap_state.read(
                household_paths, lock, required=True
            )
        self.assertEqual(pending["phase"], "BOOTSTRAP_STARTED")
        self.assertFalse(os.path.lexists(household_paths.current))

    def test_shared_operation_lock_contention_prevents_artifact_and_db_work(self) -> None:
        adapter = FakeFreshAdapter(self.source)

        with OperationLock(self.paths):
            with self.assertRaises(FreshBootstrapError):
                self._run(adapter, read_token(b"token\n"))

        self.assertNotIn("prepare-artifacts", adapter.calls)
        self.assertNotIn("start-postgres", adapter.calls)

    def test_missing_input_after_backup_is_idempotently_consumed_on_recovery(self) -> None:
        adapter = FakeFreshAdapter(self.source)
        crashed = False

        def crash_after_backup(phase: str) -> None:
            nonlocal crashed
            if phase == "BACKUP_VERIFIED" and not crashed:
                crashed = True
                raise RuntimeError("synthetic crash")

        with self.assertRaises(FreshBootstrapError):
            run_fresh_bootstrap(
                COMMAND,
                read_token(b"token\n"),
                paths=self.paths,
                adapter=adapter,
                clock=lambda: "2026-08-30T00:00:00Z",
                crash_hook=crash_after_backup,
            )
        adapter.input_exists = False

        result = self._run(adapter, read_token(b"token\n"))

        self.assertEqual(result.status, "SUCCESS")
        self.assertFalse(os.path.lexists(self.paths.pending_file))

    def test_request_mismatch_and_corrupt_state_fail_closed(self) -> None:
        adapter = FakeFreshAdapter(self.source)

        with self.assertRaises(FreshBootstrapError):
            self._run(
                adapter,
                read_token(b"token\n"),
                command=f"bootstrap-our-ledger-v1 {OTHER_REVISION} {DIGEST} actor --force",
            )
        self.assertNotIn("prepare-artifacts", adapter.calls)

        self.paths.pending_file.write_text("{}\n", encoding="utf-8")
        self.paths.pending_file.chmod(0o600)
        with self.assertRaises(FreshBootstrapError):
            self._run(FakeFreshAdapter(self.source), read_token(b"token\n"))

    def test_artifact_and_backup_mismatch_never_publish_current(self) -> None:
        artifact_adapter = FakeFreshAdapter(self.source)
        artifact_adapter.artifact_digest = OTHER_DIGEST

        with self.assertRaises(FreshBootstrapError):
            self._run(artifact_adapter, read_token(b"token\n"))

        self.assertNotIn("start-postgres", artifact_adapter.calls)
        self.assertFalse(os.path.lexists(self.paths.pending_file))
        self.assertFalse(os.path.lexists(self.paths.current))

        backup_paths = HostPaths(self.temp / "invalid-backup")
        host_state.initialize_layout(backup_paths)
        backup_adapter = FakeFreshAdapter(self._release_source("invalid-backup"))
        backup_adapter.invalid_backup = True

        with self.assertRaises(FreshBootstrapError):
            run_fresh_bootstrap(
                COMMAND,
                read_token(b"token\n"),
                paths=backup_paths,
                adapter=backup_adapter,
                clock=lambda: "2026-08-30T00:00:00Z",
            )

        with OperationLock(backup_paths) as lock:
            pending = fresh_bootstrap_state.read(backup_paths, lock, required=True)
        self.assertEqual(pending["phase"], "READINESS_VERIFIED")
        self.assertTrue(backup_adapter.input_exists)
        self.assertFalse(os.path.lexists(backup_paths.current))

    def test_token_is_bounded_zeroized_and_failure_message_is_private(self) -> None:
        with self.assertRaises(FreshBootstrapError):
            read_token(b"x" * (8 * 1024 + 1))
        token = read_token(b"private-token\n")
        adapter = FakeFreshAdapter(self.source)
        adapter.resources_exist = True

        with self.assertRaises(FreshBootstrapError) as raised:
            self._run(adapter, token)

        self.assertEqual(token, bytearray())
        self.assertEqual(str(raised.exception), "fresh bootstrap transaction failed")
        self.assertNotIn("private-token", str(raised.exception))

    def test_fixed_production_source_exposes_no_path_or_skip_override(self) -> None:
        wrapper = (ROOT / "scripts/bootstrap-production.sh").read_text(encoding="utf-8")
        source = (ROOT / "scripts/host_tools/production_fresh_bootstrap.py").read_text(
            encoding="utf-8"
        )
        combined = wrapper + source

        for forbidden in (
            "--skip-migration",
            "--skip-bootstrap",
            "--skip-backup",
            "--force",
            "shell=True",
            "HOMEOPS_REPORTER",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertNotIn("argparse", source)
        self.assertNotIn("sys.argv", source)
        self.assertNotIn('"$@"', wrapper)
        production_deploy = (
            ROOT / "scripts/host_tools/production_deploy.py"
        ).read_text(encoding="utf-8")
        self.assertIn('ENV_FILE = APP_ROOT / ".env"', production_deploy)
        self.assertIn('APP_ROOT / "household-bootstrap.json"', source)
        self.assertIn('APP_ROOT / "bootstrap-ingress"', source)
        self.assertIn('PROJECT_NAME = "our-ledger-production"', production_deploy)

    def test_input_file_helper_rejects_symlink_hardlink_mode_and_oversize(self) -> None:
        from scripts.host_tools.production_deploy import DeploymentError, _read_private_bytes

        valid = self.temp / "input.json"
        valid.write_bytes(b"{}")
        valid.chmod(0o600)
        self.assertEqual(_read_private_bytes(valid, 0o600, 8 * 1024), b"{}")

        wrong_mode = self.temp / "wrong-mode.json"
        wrong_mode.write_bytes(b"{}")
        wrong_mode.chmod(0o644)
        linked = self.temp / "linked.json"
        os.link(valid, linked)
        symlink = self.temp / "symlink.json"
        os.symlink(valid, symlink)
        oversized = self.temp / "oversized.json"
        oversized.write_bytes(b"x" * (8 * 1024 + 1))
        oversized.chmod(0o600)

        for path in (wrong_mode, linked, symlink, oversized):
            with self.subTest(path=path.name):
                with self.assertRaises((DeploymentError, OSError)):
                    _read_private_bytes(path, 0o600, 8 * 1024)

    def test_fresh_resource_discovery_includes_unlabeled_exact_project_names(self) -> None:
        from scripts.host_tools.production_fresh_bootstrap import (
            ProductionFreshBootstrapAdapter,
        )

        adapter = object.__new__(ProductionFreshBootstrapAdapter)

        def run(arguments):
            joined = " ".join(arguments)
            if "--filter label=com.docker.compose.project=" in joined:
                output = b""
            elif arguments[1:3] == ["ps", "--all"]:
                output = (
                    b"container-postgres|our-ledger-production-postgres-1\n"
                    b"container-other|unrelated-postgres-1\n"
                )
            elif arguments[1:3] == ["network", "ls"]:
                output = (
                    b"network-database|our-ledger-production_database\n"
                    b"network-other|unrelated_database\n"
                )
            elif arguments[1:3] == ["volume", "ls"]:
                output = (
                    b"our-ledger-production_postgres-data\n"
                    b"unrelated_postgres-data\n"
                )
            else:
                self.fail(f"unexpected Docker discovery command: {arguments!r}")
            return SimpleNamespace(stdout=output)

        adapter._run = run

        resources = adapter._project_resources()

        self.assertEqual(resources["containers"], ["container-postgres"])
        self.assertEqual(resources["networks"], ["network-database"])
        self.assertEqual(
            resources["volumes"], ["our-ledger-production_postgres-data"]
        )

    def _run(self, adapter, token, *, command: str = COMMAND):
        return run_fresh_bootstrap(
            command,
            token,
            paths=self.paths,
            adapter=adapter,
            clock=lambda: "2026-08-30T00:00:00Z",
        )

    def _stage(self, lock: OperationLock):
        return host_state.stage_release(
            self.paths,
            lock,
            self.source,
            application_revision=REVISION,
            runtime_config_digest=DIGEST,
            runtime_config_revision=REVISION,
        )

    def _advance_to_input_consumed(self, paths: HostPaths, lock: OperationLock) -> None:
        transitions = (
            ("ARTIFACTS_VERIFIED", "POSTGRES_STARTED", None, None),
            ("POSTGRES_STARTED", "MIGRATION_STARTED", None, None),
            ("MIGRATION_STARTED", "MIGRATION_VERIFIED", SCHEMA, None),
            ("MIGRATION_VERIFIED", "BOOTSTRAP_STARTED", None, None),
            ("BOOTSTRAP_STARTED", "BOOTSTRAP_VERIFIED", None, None),
            ("BOOTSTRAP_VERIFIED", "READINESS_VERIFIED", None, None),
            ("READINESS_VERIFIED", "BACKUP_VERIFIED", None, MARKER),
            ("BACKUP_VERIFIED", "INPUT_CONSUMED", None, None),
        )
        for current, following, schema, marker in transitions:
            fresh_bootstrap_state.advance(
                paths,
                lock,
                expected_phase=current,
                next_phase=following,
                schema_after=schema,
                backup_marker_sha256=marker,
            )

    def _release_source(self, suffix: str = "source") -> Path:
        source = self.temp / f"runtime-{suffix}"
        source.mkdir(mode=0o700)
        for relative in sorted(
            host_state.RELEASE_DIRECTORIES,
            key=lambda value: value.count("/"),
        ):
            (source / relative).mkdir(mode=0o700)
        for relative, mode in host_state.RELEASE_FILES.items():
            repository_relative = "compose.prod.yaml" if relative == "compose.yaml" else relative
            shutil.copyfile(ROOT / repository_relative, source / relative)
            (source / relative).chmod(mode)
        return source

    def _tree_fingerprint(self, root: Path) -> tuple[tuple[str, int, bytes], ...]:
        result = []
        for path in sorted(root.rglob("*")):
            details = os.lstat(path)
            relative = path.relative_to(root).as_posix()
            payload = path.read_bytes() if stat.S_ISREG(details.st_mode) else b""
            result.append((relative, stat.S_IFMT(details.st_mode), payload))
        return tuple(result)


if __name__ == "__main__":
    unittest.main()
