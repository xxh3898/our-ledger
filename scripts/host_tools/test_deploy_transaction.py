from __future__ import annotations

import base64
import io
import json
import os
import stat
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.host_tools import deploy_transaction, host_state, production_deploy


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "deploy-production.sh"
PRODUCTION_HOST = ROOT / "scripts" / "host_tools" / "production_host.py"
PRODUCTION_DEPLOY = ROOT / "scripts" / "host_tools" / "production_deploy.py"
PRODUCTION_FRESH_BOOTSTRAP = (
    ROOT / "scripts" / "host_tools" / "production_fresh_bootstrap.py"
)
FULL_CI = ROOT / ".github" / "workflows" / "full-ci.yml"
REVISION_ONE = "1" * 40
REVISION_TWO = "2" * 40
DIGEST_ONE = "sha256:" + ("a" * 64)
DIGEST_TWO = "sha256:" + ("b" * 64)
SCHEMA_V8 = host_state.SchemaAuthority("8", 0, "c" * 64)
SCHEMA_V9 = host_state.SchemaAuthority("9", 0, "d" * 64)
STARTED_AT = "2026-08-30T03:00:00Z"
FINISHED_AT = "2026-08-30T03:01:00Z"


class SyntheticCrash(BaseException):
    pass


class FakeAdapter:
    def __init__(self, paths: host_state.HostPaths, update_source: Path):
        self.paths = paths
        self.update_source = update_source
        self.calls: list[str] = []
        self.reports: list[dict[str, object]] = []
        self.fail_at: str | None = None
        self.artifact_revision = REVISION_TWO
        self.artifact_digest = DIGEST_TWO
        self.schema = SCHEMA_V8
        self.migrated_schema = SCHEMA_V8
        self.ready = True
        self.recovery_succeeds = True
        self.running_revision: str | None = REVISION_ONE
        self.persisted_revision: str | None = None
        self.cleanup_count = 0
        self.cleanup_fails = False
        self.token_reference: bytearray | None = None
        self.token_bytes_at_quiesce: int | None = None

    def validate_authority(self) -> None:
        self._call("authority")

    def prepare_artifacts(
        self,
        request: deploy_transaction.DeploymentRequest,
        token: bytearray,
        previous: host_state.ReleaseIdentity | None,
    ) -> deploy_transaction.CandidateArtifacts:
        self._call("artifacts")
        self.calls.append(f"token-bytes:{len(token)}")
        self.token_reference = token
        if request.mode == "keep":
            return deploy_transaction.CandidateArtifacts(
                revision=self.artifact_revision,
                api_reference=f"{deploy_transaction.API_REPOSITORY}:{self.artifact_revision}",
                web_reference=f"{deploy_transaction.WEB_REPOSITORY}:{self.artifact_revision}",
                runtime_config_digest=None,
                runtime_config_revision=None,
                runtime_source=None,
            )
        return deploy_transaction.CandidateArtifacts(
            revision=self.artifact_revision,
            api_reference=f"{deploy_transaction.API_REPOSITORY}:{self.artifact_revision}",
            web_reference=f"{deploy_transaction.WEB_REPOSITORY}:{self.artifact_revision}",
            runtime_config_digest=self.artifact_digest,
            runtime_config_revision=self.artifact_revision,
            runtime_source=self.update_source,
        )

    def quiesce_writer(self, previous: host_state.ReleaseIdentity | None) -> None:
        self.token_bytes_at_quiesce = len(self.token_reference or bytearray())
        self._call("quiesce")

    def run_verified_backup(self, lock: host_state.OperationLock) -> None:
        lock.assert_held(self.paths)
        self._call("backup")

    def read_schema_authority(self) -> host_state.SchemaAuthority:
        self._call("schema")
        return self.schema

    def run_candidate_migration(
        self, candidate: deploy_transaction.CandidateArtifacts
    ) -> None:
        self._call("migration")
        self.schema = self.migrated_schema

    def cutover_candidate(self, candidate: deploy_transaction.CandidateArtifacts) -> None:
        self._call("cutover")
        self.running_revision = candidate.revision

    def candidate_is_ready(self, candidate: deploy_transaction.CandidateArtifacts) -> bool:
        self._call("readiness")
        return self.ready

    def persist_candidate_images(
        self, candidate: deploy_transaction.CandidateArtifacts
    ) -> None:
        self._call("persist")
        self.persisted_revision = candidate.revision

    def recover_previous(self, previous: host_state.ReleaseIdentity | None) -> bool:
        self.calls.append("recover")
        if self.recovery_succeeds:
            self.running_revision = previous.application_revision if previous else None
        return self.recovery_succeeds

    def observe_runtime(
        self,
        candidate: host_state.ReleaseIdentity,
        previous: host_state.ReleaseIdentity | None,
    ) -> deploy_transaction.RuntimeObservation:
        self.calls.append("observe")
        return deploy_transaction.RuntimeObservation(
            schema=self.schema,
            candidate_ready=self.ready and self.running_revision == candidate.application_revision,
            previous_ready=(
                previous is not None
                and self.running_revision == previous.application_revision
            ),
            running_revision=self.running_revision,
        )

    def report_deployment(self, payload: dict[str, object]) -> None:
        self.calls.append("report")
        if self.fail_at == "report":
            raise deploy_transaction.ReporterError("synthetic reporter failure")
        self.reports.append(payload)

    def cleanup(self) -> None:
        self.cleanup_count += 1
        if self.cleanup_fails:
            raise deploy_transaction.DeploymentError("synthetic cleanup failure")

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_at == name:
            raise deploy_transaction.DeploymentError(f"synthetic {name} failure")


class DeploymentTransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary.name).resolve()
        self.paths = host_state.HostPaths(self.temp / "host")
        host_state.initialize_layout(self.paths)
        self.initial_source = self._release_source("initial")
        self.update_source = self._release_source("update")
        with host_state.OperationLock(self.paths) as lock:
            initial = host_state.stage_release(
                self.paths,
                lock,
                self.initial_source,
                application_revision=REVISION_ONE,
                runtime_config_digest=DIGEST_ONE,
                runtime_config_revision=REVISION_ONE,
            )
            host_state.begin_pending(self.paths, lock, initial)
            host_state.commit_pending(self.paths, lock)
        self.adapter = FakeAdapter(self.paths, self.update_source)
        self.command = (
            f"deploy-our-ledger-v1 {REVISION_TWO} update {DIGEST_TWO} release_actor"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_update_runs_exact_transaction_and_commits_after_readiness(self) -> None:
        token = bytearray(b"synthetic-token")

        result = self._run(token)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(token, bytearray())
        self.assertEqual(self.adapter.token_bytes_at_quiesce, 0)
        self.assertEqual(
            [
                item
                for item in self.adapter.calls
                if not item.startswith("token-bytes") and item != "report"
            ],
            [
                "authority",
                "artifacts",
                "quiesce",
                "backup",
                "schema",
                "migration",
                "schema",
                "cutover",
                "readiness",
                "persist",
            ],
        )
        with host_state.OperationLock(self.paths) as lock:
            state = host_state.inspect_state(self.paths, lock)
        self.assertFalse(state["pending"])
        self.assertEqual(state["current"]["applicationRevision"], REVISION_TWO)
        self.assertEqual(state["current"]["runtimeConfigDigest"], DIGEST_TWO)
        self.assertEqual([event["status"] for event in self.adapter.reports], ["RUNNING", "SUCCESS"])
        self.assertEqual(self.adapter.cleanup_count, 1)

    def test_keep_reuses_exact_runtime_config_identity(self) -> None:
        self.adapter.artifact_digest = DIGEST_ONE
        command = f"deploy-our-ledger-v1 {REVISION_TWO} keep release_actor"

        self._run(bytearray(b"token"), command=command)

        with host_state.OperationLock(self.paths) as lock:
            state = host_state.inspect_state(self.paths, lock)
        self.assertEqual(state["current"]["runtimeConfigDigest"], DIGEST_ONE)
        self.assertEqual(state["current"]["runtimeConfigRevision"], REVISION_ONE)
        self.assertNotIn("runtime-stage", self.adapter.calls)

    def test_keep_on_fresh_host_fails_before_artifact_or_writer(self) -> None:
        fresh_paths = host_state.HostPaths(self.temp / "fresh")
        host_state.initialize_layout(fresh_paths)
        adapter = FakeAdapter(fresh_paths, self.update_source)
        command = f"deploy-our-ledger-v1 {REVISION_TWO} keep release_actor"
        token = bytearray(b"token")

        with self.assertRaises(deploy_transaction.DeploymentError):
            deploy_transaction.run_deployment(
                command,
                token,
                paths=fresh_paths,
                adapter=adapter,
                clock=self._clock,
            )

        self.assertNotIn("artifacts", adapter.calls)
        self.assertNotIn("quiesce", adapter.calls)
        self.assertEqual(token, bytearray())

    def test_update_on_fresh_host_also_requires_explicit_future_bootstrap(self) -> None:
        fresh_paths = host_state.HostPaths(self.temp / "fresh-update")
        host_state.initialize_layout(fresh_paths)
        adapter = FakeAdapter(fresh_paths, self.update_source)
        token = bytearray(b"token")

        with self.assertRaises(deploy_transaction.DeploymentError):
            deploy_transaction.run_deployment(
                self.command,
                token,
                paths=fresh_paths,
                adapter=adapter,
                clock=self._clock,
            )

        self.assertNotIn("artifacts", adapter.calls)
        self.assertEqual(token, bytearray())

    def test_empty_multiline_or_oversized_token_fails_before_authority(self) -> None:
        invalid = (
            bytearray(),
            bytearray(b"token\nextra"),
            bytearray(b"x" * (deploy_transaction.MAX_TOKEN_BYTES + 1)),
        )
        for token in invalid:
            with self.subTest(length=len(token)):
                adapter = FakeAdapter(self.paths, self.update_source)
                with self.assertRaises(deploy_transaction.DeploymentError):
                    deploy_transaction.run_deployment(
                        self.command,
                        token,
                        paths=self.paths,
                        adapter=adapter,
                        clock=self._clock,
                    )
                self.assertEqual(adapter.calls, [])

    def test_malformed_command_zeroizes_token_and_stays_pre_authority(self) -> None:
        token = bytearray(b"private-synthetic-token")

        with self.assertRaises(deploy_transaction.DeploymentError):
            self._run(token, command=f"deploy-our-ledger-v1 {REVISION_TWO} update")

        self.assertEqual(token, bytearray())
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.adapter.cleanup_count, 1)

    def test_stdin_token_accepts_one_trailing_newline_only(self) -> None:
        token = deploy_transaction.read_token(b"synthetic-token\n")

        self.assertEqual(token, bytearray(b"synthetic-token"))
        with self.assertRaises(deploy_transaction.DeploymentError):
            deploy_transaction.read_token(b"synthetic-token\nextra")

    def test_token_is_zeroized_on_pre_pending_artifact_failure(self) -> None:
        self.adapter.fail_at = "artifacts"
        token = bytearray(b"private-synthetic-token")

        with self.assertRaises(deploy_transaction.DeploymentError):
            self._run(token)

        self.assertEqual(token, bytearray())
        self.assertFalse(self.paths.pending_file.exists())
        self.assertEqual(self.adapter.cleanup_count, 1)

    def test_revision_or_digest_mismatch_fails_before_writer_stop(self) -> None:
        cases = ((REVISION_ONE, DIGEST_TWO), (REVISION_TWO, DIGEST_ONE))
        for revision, digest in cases:
            with self.subTest(revision=revision, digest=digest):
                adapter = FakeAdapter(self.paths, self.update_source)
                adapter.artifact_revision = revision
                adapter.artifact_digest = digest
                with self.assertRaises(deploy_transaction.DeploymentError):
                    deploy_transaction.run_deployment(
                        self.command,
                        bytearray(b"token"),
                        paths=self.paths,
                        adapter=adapter,
                        clock=self._clock,
                    )
                self.assertNotIn("quiesce", adapter.calls)
                self.assertNotIn("backup", adapter.calls)
                self.assertNotIn("migration", adapter.calls)

    def test_quiesce_failure_runs_no_backup_or_migration(self) -> None:
        self.adapter.fail_at = "quiesce"

        with self.assertRaises(deploy_transaction.DeploymentError):
            self._run(bytearray(b"token"))

        self.assertNotIn("backup", self.adapter.calls)
        self.assertNotIn("migration", self.adapter.calls)
        self.assertIn("recover", self.adapter.calls)
        self.assertFalse(self.paths.pending_file.exists())
        self.assertEqual(self.adapter.reports[-1]["status"], "FAILED")

    def test_backup_failure_runs_no_migration_and_recovers_writer(self) -> None:
        self.adapter.fail_at = "backup"

        with self.assertRaises(deploy_transaction.DeploymentError):
            self._run(bytearray(b"token"))

        self.assertNotIn("migration", self.adapter.calls)
        self.assertIn("recover", self.adapter.calls)
        self.assertFalse(self.paths.pending_file.exists())
        self.assertEqual(self.adapter.running_revision, REVISION_ONE)

    def test_migration_failure_never_cuts_over(self) -> None:
        self.adapter.fail_at = "migration"

        with self.assertRaises(deploy_transaction.DeploymentError):
            self._run(bytearray(b"token"))

        self.assertNotIn("cutover", self.adapter.calls)
        self.assertIn("recover", self.adapter.calls)
        self.assertFalse(self.paths.pending_file.exists())

    def test_api_or_web_readiness_failure_with_same_schema_rolls_back(self) -> None:
        self.adapter.ready = False

        with self.assertRaises(deploy_transaction.DeploymentError):
            self._run(bytearray(b"token"))

        self.assertIn("recover", self.adapter.calls)
        self.assertEqual(self.adapter.running_revision, REVISION_ONE)
        self.assertFalse(self.paths.pending_file.exists())
        self.assertEqual(self.adapter.reports[-1]["status"], "ROLLED_BACK")
        self.assertTrue(self.adapter.reports[-1]["rollback"])

    def test_schema_change_and_readiness_failure_requires_operator(self) -> None:
        self.adapter.migrated_schema = SCHEMA_V9
        self.adapter.ready = False

        with self.assertRaises(deploy_transaction.OperatorInterventionRequired):
            self._run(bytearray(b"token"))

        self.assertNotIn("recover", self.adapter.calls)
        self.assertTrue(self.paths.pending_file.exists())
        self.assertEqual(self.adapter.running_revision, REVISION_TWO)
        self.assertEqual(self.adapter.reports[-1]["status"], "FAILED")

    def test_reporter_failure_does_not_change_application_outcome(self) -> None:
        self.adapter.fail_at = "report"

        result = self._run(bytearray(b"token"))

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(self.adapter.reports, [])
        self.assertFalse(self.paths.pending_file.exists())

    def test_cleanup_failure_is_generic_after_durable_application_commit(self) -> None:
        self.adapter.cleanup_fails = True
        token = bytearray(b"token")

        with self.assertRaisesRegex(
            deploy_transaction.DeploymentError, "deployment cleanup failed"
        ):
            self._run(token)

        self.assertEqual(token, bytearray())
        with host_state.OperationLock(self.paths) as lock:
            state = host_state.inspect_state(self.paths, lock)
        self.assertEqual(state["current"]["applicationRevision"], REVISION_TWO)
        self.assertFalse(state["pending"])

    def test_second_lock_holder_fails_without_provider_mutation(self) -> None:
        with host_state.OperationLock(self.paths):
            with self.assertRaises(deploy_transaction.DeploymentError):
                self._run(bytearray(b"token"))

        self.assertNotIn("artifacts", self.adapter.calls)
        self.assertFalse(self.paths.pending_file.exists())

    def test_crash_phases_preserve_pending_and_release_lock(self) -> None:
        phases = (
            "ARTIFACTS_VERIFIED",
            "WRITER_QUIESCED",
            "BACKUP_VERIFIED",
            "MIGRATION_STARTED",
            "MIGRATION_VERIFIED",
            "CUTOVER_STARTED",
            "READINESS_VERIFIED",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                case_root = self.temp / f"crash-{phase.lower()}"
                paths, adapter = self._ready_case(case_root)

                def crash(current: str) -> None:
                    if current == phase:
                        raise SyntheticCrash(current)

                with self.assertRaises(SyntheticCrash):
                    deploy_transaction.run_deployment(
                        self.command,
                        bytearray(b"token"),
                        paths=paths,
                        adapter=adapter,
                        clock=self._clock,
                        crash_hook=crash,
                    )

                self.assertTrue(paths.pending_file.exists())
                self.assertFalse(os.path.lexists(paths.lock))
                with host_state.OperationLock(paths) as lock:
                    pending = host_state.deployment_pending(paths, lock)
                self.assertEqual(pending["phase"], phase)

    def test_recovery_before_migration_restores_previous_and_forces_rerun(self) -> None:
        def crash(phase: str) -> None:
            if phase == "BACKUP_VERIFIED":
                raise SyntheticCrash(phase)

        with self.assertRaises(SyntheticCrash):
            self._run(bytearray(b"token"), crash_hook=crash)
        recovered_adapter = FakeAdapter(self.paths, self.update_source)
        recovered_adapter.running_revision = None

        with self.assertRaises(deploy_transaction.RecoveryCompleted):
            deploy_transaction.run_deployment(
                self.command,
                bytearray(b"new-token"),
                paths=self.paths,
                adapter=recovered_adapter,
                clock=self._clock,
            )

        self.assertIn("observe", recovered_adapter.calls)
        self.assertIn("recover", recovered_adapter.calls)
        self.assertFalse(self.paths.pending_file.exists())
        self.assertNotIn("artifacts", recovered_adapter.calls)

    def test_post_migration_changed_schema_recovery_is_fail_closed(self) -> None:
        self.adapter.migrated_schema = SCHEMA_V9

        def crash(phase: str) -> None:
            if phase == "MIGRATION_VERIFIED":
                raise SyntheticCrash(phase)

        with self.assertRaises(SyntheticCrash):
            self._run(bytearray(b"token"), crash_hook=crash)
        recovered_adapter = FakeAdapter(self.paths, self.update_source)
        recovered_adapter.schema = SCHEMA_V9

        with self.assertRaises(deploy_transaction.OperatorInterventionRequired):
            deploy_transaction.run_deployment(
                self.command,
                bytearray(b"new-token"),
                paths=self.paths,
                adapter=recovered_adapter,
                clock=self._clock,
            )

        self.assertNotIn("recover", recovered_adapter.calls)
        self.assertTrue(self.paths.pending_file.exists())

    def test_readiness_verified_crash_recovers_by_committing_candidate(self) -> None:
        def crash(phase: str) -> None:
            if phase == "READINESS_VERIFIED":
                raise SyntheticCrash(phase)

        with self.assertRaises(SyntheticCrash):
            self._run(bytearray(b"token"), crash_hook=crash)
        recovered_adapter = FakeAdapter(self.paths, self.update_source)
        recovered_adapter.running_revision = REVISION_TWO

        with host_state.OperationLock(self.paths) as lock:
            outcome = deploy_transaction.recover_pending(
                paths=self.paths,
                lock=lock,
                adapter=recovered_adapter,
                clock=self._clock,
            )

        self.assertEqual(outcome, "COMMITTED")
        self.assertEqual(recovered_adapter.persisted_revision, REVISION_TWO)
        self.assertFalse(self.paths.pending_file.exists())
        with host_state.OperationLock(self.paths) as lock:
            state = host_state.inspect_state(self.paths, lock)
        self.assertEqual(state["current"]["applicationRevision"], REVISION_TWO)

    def test_homeops_payload_matches_actual_receiver_contract(self) -> None:
        previous = self._current_identity()

        running = deploy_transaction.deployment_payload(
            revision=REVISION_TWO,
            previous=previous,
            actor="release_actor",
            started_at=STARTED_AT,
            status="RUNNING",
            finished_at=None,
            failure_stage=None,
            rollback=False,
        )
        failed = deploy_transaction.deployment_payload(
            revision=REVISION_TWO,
            previous=previous,
            actor="release_actor",
            started_at=STARTED_AT,
            status="FAILED",
            finished_at=FINISHED_AT,
            failure_stage="migration",
            rollback=False,
        )

        expected_keys = {
            "eventKey",
            "project",
            "environment",
            "branch",
            "commitSha",
            "imageTag",
            "previousCommitSha",
            "status",
            "startedAt",
            "finishedAt",
            "failureStage",
            "failureSummary",
            "actor",
            "workflowRunId",
            "workflowRunUrl",
            "rollback",
        }
        self.assertEqual(set(running), expected_keys)
        self.assertEqual(running["status"], "RUNNING")
        self.assertNotEqual(running["status"], "STARTED")
        self.assertEqual(failed["eventKey"], running["eventKey"])
        self.assertEqual(failed["failureSummary"], "deployment transaction failed")
        self.assertNotIn(str(self.paths.app_root), json.dumps(failed))

        rolled_back = deploy_transaction.deployment_payload(
            revision=REVISION_TWO,
            previous=previous,
            actor="release_actor",
            started_at=STARTED_AT,
            status="ROLLED_BACK",
            finished_at=FINISHED_AT,
            failure_stage="readiness",
            rollback=True,
        )
        self.assertEqual(rolled_back["eventKey"], running["eventKey"])
        self.assertEqual(rolled_back["failureStage"], "readiness")
        self.assertEqual(
            rolled_back["failureSummary"], "deployment transaction rolled back"
        )

    def test_invalid_homeops_status_is_not_invented(self) -> None:
        with self.assertRaises(deploy_transaction.DeploymentError):
            deploy_transaction.deployment_payload(
                revision=REVISION_TWO,
                previous=self._current_identity(),
                actor="release_actor",
                started_at=STARTED_AT,
                status="STARTED",
                finished_at=None,
                failure_stage=None,
                rollback=False,
            )

    def _run(
        self,
        token: bytearray,
        *,
        command: str | None = None,
        crash_hook=None,
    ) -> deploy_transaction.DeploymentResult:
        return deploy_transaction.run_deployment(
            command or self.command,
            token,
            paths=self.paths,
            adapter=self.adapter,
            clock=self._clock,
            crash_hook=crash_hook,
        )

    def _ready_case(
        self, root: Path
    ) -> tuple[host_state.HostPaths, FakeAdapter]:
        paths = host_state.HostPaths(root)
        host_state.initialize_layout(paths)
        initial_source = self._release_source(f"initial-{root.name}")
        update_source = self._release_source(f"update-{root.name}")
        with host_state.OperationLock(paths) as lock:
            initial = host_state.stage_release(
                paths,
                lock,
                initial_source,
                application_revision=REVISION_ONE,
                runtime_config_digest=DIGEST_ONE,
                runtime_config_revision=REVISION_ONE,
            )
            host_state.begin_pending(paths, lock, initial)
            host_state.commit_pending(paths, lock)
        return paths, FakeAdapter(paths, update_source)

    def _current_identity(self) -> host_state.ReleaseIdentity:
        with host_state.OperationLock(self.paths) as lock:
            value = host_state.inspect_state(self.paths, lock)["current"]
        return host_state.ReleaseIdentity.from_json(value)

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
    def _clock() -> str:
        return STARTED_AT


class ProductionSourceBoundaryTest(unittest.TestCase):
    def test_entrypoint_exposes_no_root_image_path_or_skip_override(self) -> None:
        wrapper = WRAPPER.read_text(encoding="utf-8")
        worker = PRODUCTION_HOST.read_text(encoding="utf-8")

        self.assertIn("scripts.host_tools.production_host deploy", wrapper)
        self.assertIn('os.environ.get("SSH_ORIGINAL_COMMAND")', worker)
        for forbidden in (
            "--root",
            "--app-root",
            "--app-dir",
            "--compose-file",
            "--state-dir",
            "--image",
            "--reporter",
            "--skip-" + "lock",
            "--skip-backup",
            "--skip-migration",
        ):
            self.assertNotIn(forbidden, wrapper)
        result = subprocess.run(
            ["python3", "-B", "-m", "scripts.host_tools.production_host", "deploy", "--root", "/tmp"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)

    def test_fixed_authorities_and_forbidden_commands_are_source_locked(self) -> None:
        source = PRODUCTION_DEPLOY.read_text(encoding="utf-8")

        for expected in (
            "/Users/homeserver/Server/backups/our-ledger/data",
            "our-ledger-production",
            '"127.0.0.1"',
            "LOOPBACK_PORT = 18080",
        ):
            self.assertIn(expected, source)
        self.assertEqual(
            production_deploy.APP_ROOT,
            Path("/Users/homeserver/Server/apps/our-ledger"),
        )
        self.assertEqual(
            production_deploy.HOMEOPS_REPORTER,
            Path(
                "/Users/homeserver/Server/apps/homeops/runtime-config/current/"
                "scripts/report-homeops-event.py"
            ),
        )
        self.assertEqual(
            (
                deploy_transaction.API_REPOSITORY,
                deploy_transaction.WEB_REPOSITORY,
                deploy_transaction.RUNTIME_CONFIG_REPOSITORY,
            ),
            (
                "ghcr.io/xxh3898/our-ledger-api",
                "ghcr.io/xxh3898/our-ledger-web",
                "ghcr.io/xxh3898/our-ledger-runtime-config",
            ),
        )
        self.assertNotIn("shell=True", source)
        self.assertNotIn("down --volumes", source)
        self.assertNotIn("docker system prune", source)
        self.assertNotIn("volume prune", source)
        self.assertNotIn("DB restore", source)
        self.assertNotIn("reverse migration", source)
        self.assertNotIn("urllib.request", source)

    def test_registry_auth_config_is_exact_private_and_helper_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            config_directory = root / "docker-config"
            config_directory.mkdir(mode=0o700)
            token = bytearray(b"synthetic-token")

            config_path = production_deploy._materialize_private_registry_auth(
                config_directory,
                "release_actor",
                token,
            )

            expected_auth = base64.b64encode(
                b"release_actor:synthetic-token"
            )
            self.assertEqual(
                config_path.read_bytes(),
                b'{"auths":{"ghcr.io":{"auth":"'
                + expected_auth
                + b'"}}}',
            )
            parsed = json.loads(config_path.read_bytes())
            self.assertEqual(set(parsed), {"auths"})
            self.assertEqual(set(parsed["auths"]), {"ghcr.io"})
            self.assertEqual(set(parsed["auths"]["ghcr.io"]), {"auth"})
            self.assertEqual(
                base64.b64decode(parsed["auths"]["ghcr.io"]["auth"]),
                b"release_actor:synthetic-token",
            )
            details = os.lstat(config_path)
            self.assertTrue(stat.S_ISREG(details.st_mode))
            self.assertEqual(details.st_uid, os.geteuid())
            self.assertEqual(stat.S_IMODE(details.st_mode), 0o600)
            self.assertEqual(details.st_nlink, 1)
            self.assertEqual(config_path.resolve(strict=True), config_path)
            self.assertEqual(stat.S_IMODE(config_directory.stat().st_mode), 0o700)
            self.assertEqual(token, bytearray(b"synthetic-token"))

        for source_path in (PRODUCTION_DEPLOY, PRODUCTION_FRESH_BOOTSTRAP):
            source = source_path.read_text(encoding="utf-8")
            for forbidden in (
                '"login"',
                '"logout"',
                "--password-stdin",
                "docker-credential-",
                "DOCKER_CONFIG",
                "Keychain",
                '"security"',
            ):
                self.assertNotIn(forbidden, source)

    def test_registry_auth_rejects_invalid_actor_or_token_before_file_creation(self) -> None:
        invalid = (
            ("", bytearray(b"token")),
            ("bad actor", bytearray(b"token")),
            ("a" * 65, bytearray(b"token")),
            ("release_actor", bytearray()),
            ("release_actor", bytearray(b"line\nfeed")),
            ("release_actor", bytearray(b"nul\0byte")),
            (
                "release_actor",
                bytearray(b"x" * (deploy_transaction.MAX_TOKEN_BYTES + 1)),
            ),
        )
        for index, (actor, token) in enumerate(invalid):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                root.chmod(0o700)
                config_directory = root / "docker-config"
                config_directory.mkdir(mode=0o700)

                with self.assertRaisesRegex(
                    deploy_transaction.DeploymentError,
                    "private registry auth input is invalid",
                ):
                    production_deploy._materialize_private_registry_auth(
                        config_directory,
                        actor,
                        token,
                    )

                self.assertFalse(os.path.lexists(config_directory / "config.json"))

    def test_registry_auth_collision_symlink_and_nonregular_targets_fail_closed(self) -> None:
        for kind in ("regular", "symlink", "directory", "fifo"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                root.chmod(0o700)
                config_directory = root / "docker-config"
                config_directory.mkdir(mode=0o700)
                config_path = config_directory / "config.json"
                protected = root / "protected"
                protected.write_bytes(b"protected-existing-bytes")
                protected.chmod(0o600)
                if kind == "regular":
                    config_path.write_bytes(b"existing-config")
                    config_path.chmod(0o600)
                elif kind == "symlink":
                    config_path.symlink_to(protected)
                elif kind == "directory":
                    config_path.mkdir(mode=0o700)
                else:
                    os.mkfifo(config_path, 0o600)
                protected_before = protected.stat()
                config_before = os.lstat(config_path)

                with self.assertRaisesRegex(
                    deploy_transaction.DeploymentError,
                    "private registry auth materialization failed",
                ):
                    production_deploy._materialize_private_registry_auth(
                        config_directory,
                        "release_actor",
                        bytearray(b"synthetic-token"),
                    )

                config_after = os.lstat(config_path)
                self.assertEqual(
                    (config_after.st_dev, config_after.st_ino),
                    (config_before.st_dev, config_before.st_ino),
                )
                self.assertEqual(protected.read_bytes(), b"protected-existing-bytes")
                protected_after = protected.stat()
                self.assertEqual(
                    (protected_after.st_dev, protected_after.st_ino),
                    (protected_before.st_dev, protected_before.st_ino),
                )

    def test_registry_auth_write_or_fsync_failure_is_generic_and_cleanup_owned(self) -> None:
        failures = (
            (
                "write",
                mock.patch.object(production_deploy.os, "write", side_effect=OSError()),
            ),
            ("zero-write", mock.patch.object(production_deploy.os, "write", return_value=0)),
            (
                "file-fsync",
                mock.patch.object(production_deploy.os, "fsync", side_effect=OSError()),
            ),
            (
                "directory-fsync",
                mock.patch.object(host_state, "_fsync_directory", side_effect=OSError()),
            ),
        )
        for name, patcher in failures:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary).resolve()
                private_root = parent / "our-ledger-deploy-synthetic"
                private_root.mkdir(mode=0o700)
                config_directory = private_root / "docker-config"
                config_directory.mkdir(mode=0o700)
                adapter = self._production_adapter(
                    host_state.HostPaths(parent / "host"), private_root
                )

                with patcher, self.assertRaisesRegex(
                    deploy_transaction.DeploymentError,
                    "private registry auth materialization failed",
                ) as raised:
                    production_deploy._materialize_private_registry_auth(
                        config_directory,
                        "release_actor",
                        bytearray(b"private-synthetic-token"),
                    )

                self.assertNotIn("private-synthetic-token", str(raised.exception))
                adapter.cleanup()
                self.assertFalse(private_root.exists())

    def test_prepare_artifacts_scopes_every_pull_to_private_config_without_token_process_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            private_root = parent / "our-ledger-deploy-synthetic"
            private_root.mkdir(mode=0o700)
            adapter = self._production_adapter(
                host_state.HostPaths(parent / "host"), private_root
            )
            runtime_source = parent / "runtime"
            runtime_source.mkdir(mode=0o700)
            adapter._extract_runtime = mock.Mock(return_value=runtime_source)
            adapter._validate_image = mock.Mock()
            adapter._validate_candidate_compose = mock.Mock()
            adapter._run = mock.Mock(
                return_value=subprocess.CompletedProcess([], 0, b"", b"")
            )
            request = deploy_transaction.DeploymentRequest(
                REVISION_TWO,
                "update",
                "release_actor",
                DIGEST_TWO,
            )
            previous = host_state.ReleaseIdentity(
                REVISION_ONE,
                DIGEST_ONE,
                REVISION_ONE,
                "c" * 64,
            )
            token = bytearray(b"private-synthetic-token")

            with mock.patch.object(
                production_deploy,
                "_create_private_temporary_root",
                return_value=private_root,
            ), mock.patch.object(production_deploy, "_require_current_images_match"):
                candidate = adapter.prepare_artifacts(request, token, previous)

            self.assertEqual(candidate.revision, REVISION_TWO)
            config_directory = private_root / "docker-config"
            commands = [call.args[0] for call in adapter._run.call_args_list]
            self.assertEqual(len(commands), 3)
            self.assertEqual(
                [command[-1] for command in commands],
                [
                    f"{deploy_transaction.API_REPOSITORY}:{REVISION_TWO}",
                    f"{deploy_transaction.WEB_REPOSITORY}:{REVISION_TWO}",
                    f"{deploy_transaction.RUNTIME_CONFIG_REPOSITORY}@{DIGEST_TWO}",
                ],
            )
            for call, command in zip(adapter._run.call_args_list, commands):
                self.assertEqual(
                    command[:4],
                    [
                        str(production_deploy.DOCKER),
                        "--config",
                        str(config_directory),
                        "pull",
                    ],
                )
                self.assertNotIn("input_bytes", call.kwargs)
            encoded = base64.b64encode(b"release_actor:private-synthetic-token")
            process_boundary = repr(adapter._run.call_args_list).encode("utf-8")
            self.assertNotIn(b"private-synthetic-token", process_boundary)
            self.assertNotIn(encoded, process_boundary)
            process_environment = production_deploy._safe_process_environment()
            self.assertEqual(set(process_environment), {"LANG", "LC_ALL", "PATH"})
            self.assertNotIn(b"private-synthetic-token", repr(process_environment).encode())
            self.assertNotIn(encoded, repr(process_environment).encode())
            self.assertEqual(token, bytearray(b"private-synthetic-token"))

            adapter.cleanup()
            self.assertFalse(private_root.exists())
            self.assertEqual(adapter._run.call_count, 3)

    def test_pull_or_identity_failure_is_generic_and_removes_private_auth(self) -> None:
        for failure in ("pull", "identity"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary).resolve()
                private_root = parent / "our-ledger-deploy-synthetic"
                private_root.mkdir(mode=0o700)
                adapter = self._production_adapter(
                    host_state.HostPaths(parent / "host"), private_root
                )
                adapter._run = mock.Mock(
                    return_value=subprocess.CompletedProcess([], 0, b"", b"")
                )
                adapter._validate_image = mock.Mock()
                if failure == "pull":
                    adapter._run.side_effect = deploy_transaction.DeploymentError(
                        "fixed production command failed"
                    )
                else:
                    adapter._validate_image.side_effect = deploy_transaction.DeploymentError(
                        "fixed production command failed"
                    )
                request = deploy_transaction.DeploymentRequest(
                    REVISION_TWO,
                    "keep",
                    "release_actor",
                    None,
                )
                previous = host_state.ReleaseIdentity(
                    REVISION_ONE,
                    DIGEST_ONE,
                    REVISION_ONE,
                    "c" * 64,
                )

                with mock.patch.object(
                    production_deploy,
                    "_create_private_temporary_root",
                    return_value=private_root,
                ), mock.patch.object(production_deploy, "_require_current_images_match"):
                    with self.assertRaisesRegex(
                        deploy_transaction.DeploymentError,
                        "fixed production command failed",
                    ) as raised:
                        adapter.prepare_artifacts(
                            request,
                            bytearray(b"private-synthetic-token"),
                            previous,
                        )

                self.assertNotIn("private-synthetic-token", str(raised.exception))
                self.assertTrue((private_root / "docker-config" / "config.json").is_file())
                adapter.cleanup()
                self.assertFalse(private_root.exists())

    @staticmethod
    def _production_adapter(
        paths: host_state.HostPaths,
        private_root: Path,
    ) -> production_deploy.ProductionDeploymentAdapter:
        adapter = object.__new__(production_deploy.ProductionDeploymentAdapter)
        adapter.paths = paths
        adapter.runtime_root = ROOT
        adapter._reporter = None
        adapter._docker_config = private_root / "docker-config"
        adapter._temporary_root = private_root
        adapter._runtime_container = None
        adapter._previous = None
        adapter._candidate = None
        adapter._candidate_release = None
        adapter._migration_started = False
        return adapter

    def test_reporter_boundary_uses_exact_executable_argument_and_stdin(self) -> None:
        source = PRODUCTION_DEPLOY.read_text(encoding="utf-8")

        self.assertIn('[str(self._reporter.path), "deployments"]', source)
        self.assertIn("input=body", source)
        self.assertIn("stdout=subprocess.DEVNULL", source)
        self.assertIn("stderr=subprocess.DEVNULL", source)
        self.assertIn("shell=False", source)
        self.assertNotIn("HOMEOPS_INGESTION_SHARED_SECRET", source)
        self.assertNotIn("smoke.origin", source)
        self.assertNotIn("/api/v1/internal/ingestion", source)

    def test_reporter_invocation_discards_output_and_maps_nonzero_or_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            reporter_path = Path(temporary).resolve() / "report-homeops-event.py"
            reporter_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            reporter_path.chmod(0o700)
            details = reporter_path.stat()
            adapter = object.__new__(production_deploy.ProductionDeploymentAdapter)
            adapter._reporter = production_deploy.monitor_worker.HomeOpsReporter(
                reporter_path,
                details.st_dev,
                details.st_ino,
            )
            payload = {"eventKey": "synthetic-deployment"}

            accepted = subprocess.CompletedProcess(
                [str(reporter_path), "deployments"], 0, b"", b""
            )
            with mock.patch.object(
                production_deploy.subprocess, "run", return_value=accepted
            ) as runner:
                adapter.report_deployment(payload)

            arguments, keywords = runner.call_args
            self.assertEqual(arguments[0], [str(reporter_path), "deployments"])
            self.assertEqual(
                keywords["input"],
                b'{"eventKey":"synthetic-deployment"}',
            )
            self.assertIs(keywords["stdout"], subprocess.DEVNULL)
            self.assertIs(keywords["stderr"], subprocess.DEVNULL)
            self.assertFalse(keywords["shell"])
            self.assertEqual(keywords["env"], production_deploy._safe_process_environment())

            failures = (
                subprocess.CompletedProcess(arguments[0], 1, b"", b""),
                subprocess.TimeoutExpired(arguments[0], 1),
            )
            for failure in failures:
                with self.subTest(failure=type(failure).__name__):
                    patcher = (
                        mock.patch.object(
                            production_deploy.subprocess, "run", side_effect=failure
                        )
                        if isinstance(failure, BaseException)
                        else mock.patch.object(
                            production_deploy.subprocess, "run", return_value=failure
                        )
                    )
                    with patcher, self.assertRaisesRegex(
                        deploy_transaction.ReporterError,
                        "HomeOps reporter did not accept deployment",
                    ):
                        adapter.report_deployment(payload)

    def test_candidate_subprocess_environment_drops_ambient_authority(self) -> None:
        candidate = deploy_transaction.CandidateArtifacts(
            revision=REVISION_TWO,
            api_reference=f"{deploy_transaction.API_REPOSITORY}:{REVISION_TWO}",
            web_reference=f"{deploy_transaction.WEB_REPOSITORY}:{REVISION_TWO}",
            runtime_config_digest=None,
            runtime_config_revision=None,
            runtime_source=None,
        )
        with mock.patch.dict(
            os.environ,
            {
                "DOCKER_HOST": "tcp://untrusted.invalid:2375",
                "POSTGRES_PASSWORD": "ambient-private-value",
                "OUR_LEDGER_API_IMAGE": "untrusted-image",
            },
            clear=True,
        ):
            environment = production_deploy._candidate_environment(candidate)

        self.assertNotIn("DOCKER_HOST", environment)
        self.assertNotIn("POSTGRES_PASSWORD", environment)
        self.assertEqual(environment["OUR_LEDGER_API_IMAGE"], candidate.api_reference)
        self.assertEqual(environment["OUR_LEDGER_WEB_IMAGE"], candidate.web_reference)

    def test_image_inspect_rejects_wrong_id_architecture_repository_revision_or_digest(self) -> None:
        repository = deploy_transaction.API_REPOSITORY
        digest = "sha256:" + ("e" * 64)
        valid = {
            "Id": "sha256:" + ("f" * 64),
            "Os": "linux",
            "Architecture": "arm64",
            "RepoDigests": [f"{repository}@{digest}"],
            "Config": {
                "Labels": {
                    "org.opencontainers.image.source": production_deploy.SOURCE_URL,
                    "org.opencontainers.image.revision": REVISION_TWO,
                    "org.opencontainers.image.version": REVISION_TWO,
                }
            },
        }
        adapter = object.__new__(production_deploy.ProductionDeploymentAdapter)

        def validate(value: dict[str, object], expected_digest: str | None = None) -> None:
            adapter._run = mock.Mock(
                return_value=subprocess.CompletedProcess(
                    [], 0, json.dumps([value]).encode("utf-8"), b""
                )
            )
            adapter._validate_image(
                f"{repository}:{REVISION_TWO}",
                repository,
                REVISION_TWO,
                expected_digest=expected_digest,
            )

        validate(valid, digest)
        invalid_values = []
        for mutate in (
            lambda value: value.update({"Id": "sha256:short"}),
            lambda value: value.update({"Architecture": "amd64"}),
            lambda value: value.update(
                {"RepoDigests": [f"ghcr.io/xxh3898/other@{digest}"]}
            ),
            lambda value: value["Config"]["Labels"].update(
                {"org.opencontainers.image.revision": REVISION_ONE}
            ),
        ):
            value = json.loads(json.dumps(valid))
            mutate(value)
            invalid_values.append(value)
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(
                deploy_transaction.DeploymentError
            ):
                validate(value, digest)
        with self.assertRaises(deploy_transaction.DeploymentError):
            validate(valid, "sha256:" + ("9" * 64))

    def test_image_env_update_changes_only_two_keys_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            env = root / ".env"
            env.write_text(
                "OUR_LEDGER_API_IMAGE=old-api\n"
                "POSTGRES_PASSWORD=synthetic-private-value\n"
                "OUR_LEDGER_WEB_IMAGE=old-web\n",
                encoding="utf-8",
            )
            env.chmod(0o600)

            production_deploy._replace_env_images(
                env,
                f"{deploy_transaction.API_REPOSITORY}:{REVISION_TWO}",
                f"{deploy_transaction.WEB_REPOSITORY}:{REVISION_TWO}",
            )

            value = env.read_text(encoding="utf-8")
            self.assertIn("POSTGRES_PASSWORD=synthetic-private-value", value)
            self.assertEqual(value.count("OUR_LEDGER_API_IMAGE="), 1)
            self.assertEqual(value.count("OUR_LEDGER_WEB_IMAGE="), 1)
            self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_runtime_archive_rejects_symlink_and_accepts_exact_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "runtime.tar"
            self._write_runtime_archive(archive)
            destination = root / "runtime"

            production_deploy._extract_verified_runtime(archive, destination)

            actual_files = {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual_files, set(host_state.RELEASE_FILES))
            for relative, mode in host_state.RELEASE_FILES.items():
                target = destination / relative
                self.assertEqual(target.read_text(encoding="utf-8"), f"{relative}\n")
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), mode)

            unsafe = root / "unsafe.tar"
            with tarfile.open(unsafe, "w") as bundle:
                member = tarfile.TarInfo("runtime/compose.yaml")
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/outside"
                bundle.addfile(member)
            with self.assertRaises(deploy_transaction.DeploymentError):
                production_deploy._extract_verified_runtime(unsafe, root / "unsafe")

    def test_dedicated_gate_is_wired_without_network_or_production_access(self) -> None:
        local = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        hosted = FULL_CI.read_text(encoding="utf-8")
        gate = (ROOT / "scripts" / "verify-host-deploy-transaction.sh")

        self.assertTrue(gate.is_file())
        source = gate.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\b(?:curl|gh|ssh|tailscale)\b|docker\s+(?:login|pull|push)")
        self.assertIn("verify-host-deploy-transaction.sh", local)
        self.assertIn("  host-deploy-transaction:\n", hosted)

    @staticmethod
    def _write_runtime_archive(path: Path) -> None:
        with tarfile.open(path, "w") as bundle:
            root = tarfile.TarInfo("runtime")
            root.type = tarfile.DIRTYPE
            root.mode = 0o755
            bundle.addfile(root)
            for relative in sorted(
                host_state.RELEASE_DIRECTORIES,
                key=lambda item: item.count("/"),
            ):
                member = tarfile.TarInfo(f"runtime/{relative}")
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                bundle.addfile(member)
            for relative, mode in host_state.RELEASE_FILES.items():
                payload = f"{relative}\n".encode("utf-8")
                member = tarfile.TarInfo(f"runtime/{relative}")
                member.size = len(payload)
                member.mode = mode
                bundle.addfile(member, io.BytesIO(payload))


if __name__ == "__main__":
    unittest.main()
