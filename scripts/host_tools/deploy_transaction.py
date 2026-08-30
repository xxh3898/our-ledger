from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from scripts.host_tools import host_state
from scripts.host_tools.host_state import (
    ContractError,
    HostPaths,
    OperationLock,
    ReleaseIdentity,
    SchemaAuthority,
)
from scripts.release_tools import release_contract


API_REPOSITORY = "ghcr.io/xxh3898/our-ledger-api"
WEB_REPOSITORY = "ghcr.io/xxh3898/our-ledger-web"
RUNTIME_CONFIG_REPOSITORY = "ghcr.io/xxh3898/our-ledger-runtime-config"
PROJECT = "our-ledger"
ENVIRONMENT = "production"
BRANCH = "main"
MAX_TOKEN_BYTES = 8 * 1024


class DeploymentError(ContractError):
    pass


class OperatorInterventionRequired(DeploymentError):
    pass


class RecoveryCompleted(DeploymentError):
    pass


class ReporterError(DeploymentError):
    pass


@dataclass(frozen=True)
class DeploymentRequest:
    revision: str
    mode: str
    actor: str
    runtime_config_digest: str | None

    @classmethod
    def from_command(cls, value: str) -> "DeploymentRequest":
        try:
            parsed = release_contract.parse_command(value)
        except release_contract.ContractError as error:
            raise DeploymentError("restricted deployment command is invalid") from error
        return cls(
            revision=parsed["revision"],
            mode=parsed["mode"],
            actor=parsed["actor"],
            runtime_config_digest=parsed["runtimeConfigDigest"],
        )


@dataclass(frozen=True)
class CandidateArtifacts:
    revision: str
    api_reference: str
    web_reference: str
    runtime_config_digest: str | None
    runtime_config_revision: str | None
    runtime_source: Path | None

    def validate_for(self, request: DeploymentRequest) -> None:
        if self.revision != request.revision:
            raise DeploymentError("candidate revision differs")
        if self.api_reference != f"{API_REPOSITORY}:{request.revision}":
            raise DeploymentError("candidate API image authority differs")
        if self.web_reference != f"{WEB_REPOSITORY}:{request.revision}":
            raise DeploymentError("candidate Web image authority differs")
        if request.mode == "keep":
            if any(
                item is not None
                for item in (
                    self.runtime_config_digest,
                    self.runtime_config_revision,
                    self.runtime_source,
                )
            ):
                raise DeploymentError("keep candidate contains runtime config material")
            return
        if (
            self.runtime_config_digest != request.runtime_config_digest
            or self.runtime_config_revision != request.revision
            or self.runtime_source is None
            or not self.runtime_source.is_absolute()
        ):
            raise DeploymentError("update candidate runtime config authority differs")


@dataclass(frozen=True)
class RuntimeObservation:
    schema: SchemaAuthority
    candidate_ready: bool
    previous_ready: bool
    running_revision: str | None


class DeploymentAdapter(Protocol):
    def validate_authority(self) -> None: ...

    def prepare_artifacts(
        self,
        request: DeploymentRequest,
        token: bytearray,
        previous: ReleaseIdentity | None,
    ) -> CandidateArtifacts: ...

    def quiesce_writer(self, previous: ReleaseIdentity | None) -> None: ...

    def run_verified_backup(self, lock: OperationLock) -> None: ...

    def read_schema_authority(self) -> SchemaAuthority: ...

    def run_candidate_migration(self, candidate: CandidateArtifacts) -> None: ...

    def cutover_candidate(self, candidate: CandidateArtifacts) -> None: ...

    def candidate_is_ready(self, candidate: CandidateArtifacts) -> bool: ...

    def persist_candidate_images(self, candidate: CandidateArtifacts) -> None: ...

    def recover_previous(self, previous: ReleaseIdentity | None) -> bool: ...

    def observe_runtime(
        self,
        candidate: ReleaseIdentity,
        previous: ReleaseIdentity | None,
    ) -> RuntimeObservation: ...

    def report_deployment(self, payload: dict[str, object]) -> None: ...

    def cleanup(self) -> None: ...


@dataclass(frozen=True)
class DeploymentResult:
    revision: str
    status: str


Clock = Callable[[], str]
CrashHook = Callable[[str], None]


def run_deployment(
    command: str,
    token: bytearray,
    *,
    paths: HostPaths,
    adapter: DeploymentAdapter,
    clock: Clock,
    crash_hook: CrashHook | None = None,
) -> DeploymentResult:
    stage = "authority"
    pending_started = False
    writer_quiesce_attempted = False
    cutover_started = False
    request: DeploymentRequest | None = None
    previous: ReleaseIdentity | None = None
    started_at: str | None = None

    try:
        request = DeploymentRequest.from_command(command)
        _validate_token(token)
        started_at = clock()
        adapter.validate_authority()
        with OperationLock(paths) as lock:
            state = host_state.inspect_state(paths, lock)
            if state["pending"]:
                recover_pending(paths=paths, lock=lock, adapter=adapter, clock=clock)
                raise RecoveryCompleted("existing deployment recovery completed")

            previous_value = state["current"]
            previous = (
                ReleaseIdentity.from_json(previous_value)
                if previous_value is not None
                else None
            )
            if previous is None:
                raise DeploymentError("deployment requires a verified current release")

            stage = "artifacts"
            artifacts = adapter.prepare_artifacts(request, token, previous)
            artifacts.validate_for(request)
            _zeroize(token)
            candidate = _stage_candidate(
                paths=paths,
                lock=lock,
                request=request,
                artifacts=artifacts,
                previous=previous,
            )
            host_state.begin_deployment_pending(
                paths,
                lock,
                candidate,
                actor=request.actor,
                started_at=started_at,
            )
            pending_started = True
            _report_pending(adapter, paths, lock, "RUNNING", None, None, False)
            _crash(crash_hook, "ARTIFACTS_VERIFIED")

            stage = "writer-quiesce"
            writer_quiesce_attempted = True
            adapter.quiesce_writer(previous)
            host_state.advance_deployment_pending(
                paths,
                lock,
                expected_phase="ARTIFACTS_VERIFIED",
                next_phase="WRITER_QUIESCED",
            )
            _crash(crash_hook, "WRITER_QUIESCED")

            stage = "predeploy-backup"
            adapter.run_verified_backup(lock)
            schema_before = adapter.read_schema_authority()
            host_state.advance_deployment_pending(
                paths,
                lock,
                expected_phase="WRITER_QUIESCED",
                next_phase="BACKUP_VERIFIED",
                schema_before=schema_before,
            )
            _crash(crash_hook, "BACKUP_VERIFIED")

            stage = "migration"
            host_state.advance_deployment_pending(
                paths,
                lock,
                expected_phase="BACKUP_VERIFIED",
                next_phase="MIGRATION_STARTED",
            )
            _crash(crash_hook, "MIGRATION_STARTED")
            adapter.run_candidate_migration(artifacts)
            schema_after = adapter.read_schema_authority()
            host_state.advance_deployment_pending(
                paths,
                lock,
                expected_phase="MIGRATION_STARTED",
                next_phase="MIGRATION_VERIFIED",
                schema_after=schema_after,
            )
            _crash(crash_hook, "MIGRATION_VERIFIED")

            stage = "candidate-cutover"
            host_state.advance_deployment_pending(
                paths,
                lock,
                expected_phase="MIGRATION_VERIFIED",
                next_phase="CUTOVER_STARTED",
            )
            cutover_started = True
            adapter.cutover_candidate(artifacts)
            _crash(crash_hook, "CUTOVER_STARTED")

            stage = "readiness"
            if not adapter.candidate_is_ready(artifacts):
                raise DeploymentError("candidate readiness contract failed")
            host_state.advance_deployment_pending(
                paths,
                lock,
                expected_phase="CUTOVER_STARTED",
                next_phase="READINESS_VERIFIED",
            )
            _crash(crash_hook, "READINESS_VERIFIED")

            stage = "commit"
            adapter.persist_candidate_images(artifacts)
            host_state.commit_pending(paths, lock)
            pending_started = False
            _safe_report(
                adapter,
                deployment_payload(
                    revision=request.revision,
                    previous=previous,
                    actor=request.actor,
                    started_at=started_at,
                    status="SUCCESS",
                    finished_at=clock(),
                    failure_stage=None,
                    rollback=False,
                ),
            )
            return DeploymentResult(request.revision, "SUCCESS")
    except (RecoveryCompleted, OperatorInterventionRequired):
        raise
    except Exception as error:
        if pending_started:
            assert request is not None
            assert started_at is not None
            status = _recover_failed_transaction(
                paths=paths,
                adapter=adapter,
                previous=previous,
                writer_quiesce_attempted=writer_quiesce_attempted,
                cutover_started=cutover_started,
            )
            failure_stage = stage if status != "OPERATOR_INTERVENTION" else "recovery"
            _safe_report(
                adapter,
                deployment_payload(
                    revision=request.revision,
                    previous=previous,
                    actor=request.actor,
                    started_at=started_at,
                    status="ROLLED_BACK" if status == "ROLLED_BACK" else "FAILED",
                    finished_at=clock(),
                    failure_stage=failure_stage,
                    rollback=status == "ROLLED_BACK",
                ),
            )
            if status == "OPERATOR_INTERVENTION":
                raise OperatorInterventionRequired(
                    "deployment requires operator intervention"
                ) from error
        raise DeploymentError("deployment transaction failed") from error
    finally:
        _zeroize(token)
        active_error = sys.exc_info()[0] is not None
        try:
            adapter.cleanup()
        except Exception as cleanup_error:
            if not active_error:
                raise DeploymentError("deployment cleanup failed") from cleanup_error


def recover_pending(
    *,
    paths: HostPaths,
    lock: OperationLock,
    adapter: DeploymentAdapter,
    clock: Clock,
) -> str:
    pending = host_state.deployment_pending(paths, lock)
    if pending is None:
        raise DeploymentError("deployment recovery requires pending state")
    phase = pending["phase"]
    if phase == "STAGED":
        raise OperatorInterventionRequired("B1 staging recovery is separate")
    candidate = pending["candidate"]
    previous = pending["previous"]
    assert isinstance(candidate, ReleaseIdentity)
    assert previous is None or isinstance(previous, ReleaseIdentity)
    observation = adapter.observe_runtime(candidate, previous)
    schema_before = pending["schemaBefore"]
    schema_after = pending["schemaAfter"]

    if phase in {"READINESS_VERIFIED", "COMMITTING"}:
        if (
            observation.candidate_ready
            and observation.running_revision == candidate.application_revision
            and isinstance(schema_after, SchemaAuthority)
            and observation.schema == schema_after
        ):
            if phase == "READINESS_VERIFIED":
                synthetic = CandidateArtifacts(
                    revision=candidate.application_revision,
                    api_reference=f"{API_REPOSITORY}:{candidate.application_revision}",
                    web_reference=f"{WEB_REPOSITORY}:{candidate.application_revision}",
                    runtime_config_digest=None,
                    runtime_config_revision=None,
                    runtime_source=None,
                )
                adapter.persist_candidate_images(synthetic)
                host_state.commit_pending(paths, lock)
            else:
                host_state.finish_committed_pending(paths, lock)
            _safe_report_for_snapshot(
                adapter,
                pending,
                status="SUCCESS",
                finished_at=clock(),
                failure_stage=None,
                rollback=False,
            )
            return "COMMITTED"
        raise OperatorInterventionRequired(
            "readiness-verified deployment cannot be safely finalized"
        )

    migration_may_have_run = phase in {
        "MIGRATION_STARTED",
        "MIGRATION_VERIFIED",
        "CUTOVER_STARTED",
    }
    if migration_may_have_run:
        if not isinstance(schema_before, SchemaAuthority):
            raise OperatorInterventionRequired("schema predecessor is unavailable")
        if observation.schema != schema_before:
            raise OperatorInterventionRequired("schema authority changed")
    elif isinstance(schema_before, SchemaAuthority) and observation.schema != schema_before:
        raise OperatorInterventionRequired("schema authority changed before migration")

    if not adapter.recover_previous(previous):
        raise OperatorInterventionRequired("previous runtime recovery failed")
    host_state.clear_recovered_deployment_pending(paths, lock)
    _safe_report_for_snapshot(
        adapter,
        pending,
        status="ROLLED_BACK" if phase == "CUTOVER_STARTED" else "FAILED",
        finished_at=clock(),
        failure_stage="recovery",
        rollback=phase == "CUTOVER_STARTED",
    )
    return "ROLLED_BACK" if phase == "CUTOVER_STARTED" else "RECOVERED"


def deployment_payload(
    *,
    revision: str,
    previous: ReleaseIdentity | None,
    actor: str,
    started_at: str,
    status: str,
    finished_at: str | None,
    failure_stage: str | None,
    rollback: bool,
) -> dict[str, object]:
    if status not in {"RUNNING", "SUCCESS", "FAILED", "ROLLED_BACK"}:
        raise DeploymentError("HomeOps deployment status is unsupported")
    event_suffix = hashlib.sha256(started_at.encode("utf-8")).hexdigest()[:16]
    failed = status in {"FAILED", "ROLLED_BACK"}
    return {
        "eventKey": f"our-ledger:deploy:{revision}:{event_suffix}",
        "project": PROJECT,
        "environment": ENVIRONMENT,
        "branch": BRANCH,
        "commitSha": revision,
        "imageTag": revision,
        "previousCommitSha": previous.application_revision if previous else None,
        "status": status,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "failureStage": failure_stage if failed else None,
        "failureSummary": (
            "deployment transaction rolled back"
            if status == "ROLLED_BACK"
            else "deployment transaction failed" if failed else None
        ),
        "actor": actor,
        "workflowRunId": None,
        "workflowRunUrl": None,
        "rollback": rollback,
    }


def read_token(source: bytes) -> bytearray:
    token = bytearray(source)
    try:
        if len(token) > MAX_TOKEN_BYTES + 1:
            raise DeploymentError("registry token input is too large")
        if token.endswith(b"\n"):
            del token[-1]
        _validate_token(token)
        return token
    except Exception:
        _zeroize(token)
        raise


def _stage_candidate(
    *,
    paths: HostPaths,
    lock: OperationLock,
    request: DeploymentRequest,
    artifacts: CandidateArtifacts,
    previous: ReleaseIdentity | None,
) -> ReleaseIdentity:
    if request.mode == "keep":
        if previous is None:
            raise DeploymentError("keep deployment requires a current release")
        return ReleaseIdentity(
            application_revision=request.revision,
            runtime_config_digest=previous.runtime_config_digest,
            runtime_config_revision=previous.runtime_config_revision,
            runtime_config_content_sha256=previous.runtime_config_content_sha256,
        )
    assert artifacts.runtime_source is not None
    assert artifacts.runtime_config_digest is not None
    assert artifacts.runtime_config_revision is not None
    return host_state.stage_release(
        paths,
        lock,
        artifacts.runtime_source,
        application_revision=request.revision,
        runtime_config_digest=artifacts.runtime_config_digest,
        runtime_config_revision=artifacts.runtime_config_revision,
    )


def _recover_failed_transaction(
    *,
    paths: HostPaths,
    adapter: DeploymentAdapter,
    previous: ReleaseIdentity | None,
    writer_quiesce_attempted: bool,
    cutover_started: bool,
) -> str:
    try:
        with OperationLock(paths) as lock:
            pending = host_state.deployment_pending(paths, lock)
            if pending is None:
                return "FAILED"
            phase = pending["phase"]
            schema_before = pending["schemaBefore"]
            migration_may_have_run = phase in {
                "MIGRATION_STARTED",
                "MIGRATION_VERIFIED",
                "CUTOVER_STARTED",
                "READINESS_VERIFIED",
                "COMMITTING",
            }
            if migration_may_have_run:
                if not isinstance(schema_before, SchemaAuthority):
                    return "OPERATOR_INTERVENTION"
                if adapter.read_schema_authority() != schema_before:
                    return "OPERATOR_INTERVENTION"
            if writer_quiesce_attempted or cutover_started:
                if not adapter.recover_previous(previous):
                    return "OPERATOR_INTERVENTION"
            host_state.clear_recovered_deployment_pending(paths, lock)
            return "ROLLED_BACK" if cutover_started else "FAILED"
    except (ContractError, OSError):
        return "OPERATOR_INTERVENTION"


def _report_pending(
    adapter: DeploymentAdapter,
    paths: HostPaths,
    lock: OperationLock,
    status: str,
    finished_at: str | None,
    failure_stage: str | None,
    rollback: bool,
) -> None:
    pending = host_state.deployment_pending(paths, lock)
    if pending is None:
        raise DeploymentError("deployment reporting requires pending state")
    _safe_report_for_snapshot(
        adapter,
        pending,
        status=status,
        finished_at=finished_at,
        failure_stage=failure_stage,
        rollback=rollback,
    )


def _safe_report_for_snapshot(
    adapter: DeploymentAdapter,
    pending: dict[str, object],
    *,
    status: str,
    finished_at: str | None,
    failure_stage: str | None,
    rollback: bool,
) -> None:
    candidate = pending["candidate"]
    previous = pending["previous"]
    assert isinstance(candidate, ReleaseIdentity)
    assert previous is None or isinstance(previous, ReleaseIdentity)
    _safe_report(
        adapter,
        deployment_payload(
            revision=candidate.application_revision,
            previous=previous,
            actor=pending["actor"],
            started_at=pending["startedAt"],
            status=status,
            finished_at=finished_at,
            failure_stage=failure_stage,
            rollback=rollback,
        ),
    )


def _safe_report(
    adapter: DeploymentAdapter,
    payload: dict[str, object],
) -> None:
    try:
        adapter.report_deployment(payload)
    except (ReporterError, OSError):
        return


def _validate_token(token: bytearray) -> None:
    if (
        not isinstance(token, bytearray)
        or not token
        or len(token) > MAX_TOKEN_BYTES
        or any(value in token for value in (0, 10, 13))
    ):
        raise DeploymentError("registry token input is invalid")


def _zeroize(token: bytearray) -> None:
    if isinstance(token, bytearray):
        for index in range(len(token)):
            token[index] = 0
        token.clear()


def _crash(hook: CrashHook | None, phase: str) -> None:
    if hook is not None:
        hook(phase)
