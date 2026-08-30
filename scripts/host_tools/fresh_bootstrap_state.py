from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

from scripts.host_tools import host_state
from scripts.host_tools.host_state import (
    ContractError,
    HostPaths,
    OperationLock,
    ReleaseIdentity,
    SchemaAuthority,
)


TRANSACTION_KIND = "FRESH_BOOTSTRAP"
FRESH_PHASES = (
    "ARTIFACTS_VERIFIED",
    "POSTGRES_STARTED",
    "MIGRATION_STARTED",
    "MIGRATION_VERIFIED",
    "BOOTSTRAP_STARTED",
    "BOOTSTRAP_VERIFIED",
    "READINESS_VERIFIED",
    "BACKUP_VERIFIED",
    "INPUT_CONSUMED",
    "COMMITTING",
)
FRESH_PHASE_TRANSITIONS = {
    current: following for current, following in zip(FRESH_PHASES, FRESH_PHASES[1:])
}
FRESH_PENDING_KEYS = frozenset(
    {
        "formatVersion",
        "project",
        "transactionKind",
        "phase",
        "candidate",
        "previous",
        "actor",
        "startedAt",
        "schemaAfter",
        "backupMarkerSha256",
    }
)


def begin(
    paths: HostPaths,
    lock: OperationLock,
    candidate: ReleaseIdentity,
    *,
    actor: str,
    started_at: str,
) -> None:
    lock.assert_held(paths)
    _require_fresh_committed_authority(paths)
    if os.path.lexists(paths.pending_file):
        raise ContractError("fresh bootstrap pending transaction already exists")
    host_state._require_identity_release(paths, candidate)
    _write(
        paths,
        {
            "phase": FRESH_PHASES[0],
            "candidate": candidate,
            "actor": host_state._require_actor(actor),
            "startedAt": host_state._require_instant(started_at),
            "schemaAfter": None,
            "backupMarkerSha256": None,
        },
    )


def read(
    paths: HostPaths,
    lock: OperationLock,
    *,
    required: bool = False,
) -> dict[str, object] | None:
    lock.assert_held(paths)
    return _read(paths, required=required)


def advance(
    paths: HostPaths,
    lock: OperationLock,
    *,
    expected_phase: str,
    next_phase: str,
    schema_after: SchemaAuthority | None = None,
    backup_marker_sha256: str | None = None,
) -> None:
    lock.assert_held(paths)
    pending = _read(paths, required=True)
    assert pending is not None
    if pending["phase"] != expected_phase:
        raise ContractError("fresh bootstrap pending phase differs")
    if FRESH_PHASE_TRANSITIONS.get(expected_phase) != next_phase:
        raise ContractError("fresh bootstrap pending phase transition is invalid")

    current_schema = pending["schemaAfter"]
    if schema_after is not None:
        if current_schema is not None and current_schema != schema_after:
            raise ContractError("fresh bootstrap schema authority differs")
        current_schema = schema_after

    current_marker = pending["backupMarkerSha256"]
    if backup_marker_sha256 is not None:
        _require_sha256(backup_marker_sha256)
        if current_marker is not None and current_marker != backup_marker_sha256:
            raise ContractError("fresh bootstrap backup authority differs")
        current_marker = backup_marker_sha256

    if FRESH_PHASES.index(next_phase) >= FRESH_PHASES.index("MIGRATION_VERIFIED"):
        if current_schema is None:
            raise ContractError("fresh bootstrap schema authority is missing")
    if FRESH_PHASES.index(next_phase) >= FRESH_PHASES.index("BACKUP_VERIFIED"):
        if current_marker is None:
            raise ContractError("fresh bootstrap backup authority is missing")

    _write(
        paths,
        {
            **pending,
            "phase": next_phase,
            "schemaAfter": current_schema,
            "backupMarkerSha256": current_marker,
        },
    )


def commit(
    paths: HostPaths,
    lock: OperationLock,
    *,
    after_current: Callable[[], None] | None = None,
    after_state: Callable[[], None] | None = None,
) -> ReleaseIdentity:
    lock.assert_held(paths)
    pending = _read(paths, required=True)
    assert pending is not None
    if pending["phase"] == "INPUT_CONSUMED":
        _write(paths, {**pending, "phase": "COMMITTING"})
        pending = _read(paths, required=True)
        assert pending is not None
    elif pending["phase"] != "COMMITTING":
        raise ContractError("fresh bootstrap transaction is not ready to commit")

    candidate = pending["candidate"]
    assert isinstance(candidate, ReleaseIdentity)
    _require_commit_observation(paths, candidate)
    if _read_fresh_current(paths, candidate) is None:
        host_state._write_current(paths, candidate)
    if after_current is not None:
        after_current()

    committed = host_state._read_committed_identity(paths)
    if committed is None:
        host_state._atomic_write_json(
            paths.state_file,
            {
                "formatVersion": host_state.FORMAT_VERSION,
                "project": host_state.PROJECT,
                "current": candidate.to_json(),
                "previous": None,
            },
        )
    elif committed != candidate:
        raise ContractError("fresh bootstrap committed state differs")
    if after_state is not None:
        after_state()

    host_state._unlink_regular_file(paths.pending_file, 0o600)
    return candidate


def inspect(paths: HostPaths, lock: OperationLock) -> dict[str, object]:
    lock.assert_held(paths)
    pending = _read(paths, required=False)
    committed = host_state._read_committed_identity(paths)
    if pending is None:
        current = host_state._read_current_identity(paths)
        if committed != current:
            raise ContractError("fresh bootstrap committed authority differs")
        return {
            "status": "READY" if current else "FRESH",
            "pending": None,
            "current": current,
        }

    candidate = pending["candidate"]
    assert isinstance(candidate, ReleaseIdentity)
    current = _read_fresh_current(paths, candidate)
    if pending["phase"] == "COMMITTING":
        if current not in (None, candidate) or committed not in (None, candidate):
            raise ContractError("fresh bootstrap committing authority differs")
    elif current is not None or committed is not None:
        raise ContractError("fresh bootstrap published before commit")
    return {"status": "PENDING", "pending": pending, "current": current}


def _read(paths: HostPaths, *, required: bool) -> dict[str, object] | None:
    if not os.path.lexists(paths.pending_file):
        if required:
            raise ContractError("fresh bootstrap pending transaction is missing")
        return None
    value = host_state._read_json(paths.pending_file, FRESH_PENDING_KEYS)
    if (
        type(value["formatVersion"]) is not int
        or value["formatVersion"] != host_state.FORMAT_VERSION
        or value["project"] != host_state.PROJECT
        or value["transactionKind"] != TRANSACTION_KIND
        or value["phase"] not in FRESH_PHASES
        or value["previous"] is not None
    ):
        raise ContractError("fresh bootstrap pending authority is invalid")

    candidate = ReleaseIdentity.from_json(value["candidate"])
    host_state._require_identity_release(paths, candidate)
    actor = host_state._require_actor(value["actor"])
    started_at = host_state._require_instant(value["startedAt"])
    phase = value["phase"]
    phase_index = FRESH_PHASES.index(phase)
    schema_after = (
        SchemaAuthority.from_json(value["schemaAfter"])
        if value["schemaAfter"] is not None
        else None
    )
    marker = value["backupMarkerSha256"]
    if marker is not None:
        _require_sha256(marker)
    if (phase_index >= FRESH_PHASES.index("MIGRATION_VERIFIED")) != (
        schema_after is not None
    ):
        raise ContractError("fresh bootstrap schema authority presence differs")
    if (phase_index >= FRESH_PHASES.index("BACKUP_VERIFIED")) != (marker is not None):
        raise ContractError("fresh bootstrap backup authority presence differs")
    return {
        "phase": phase,
        "candidate": candidate,
        "actor": actor,
        "startedAt": started_at,
        "schemaAfter": schema_after,
        "backupMarkerSha256": marker,
    }


def _write(paths: HostPaths, pending: dict[str, object]) -> None:
    candidate = pending["candidate"]
    if not isinstance(candidate, ReleaseIdentity):
        raise ContractError("fresh bootstrap candidate identity is invalid")
    schema_after = pending["schemaAfter"]
    if schema_after is not None and not isinstance(schema_after, SchemaAuthority):
        raise ContractError("fresh bootstrap schema authority is invalid")
    payload = {
        "formatVersion": host_state.FORMAT_VERSION,
        "project": host_state.PROJECT,
        "transactionKind": TRANSACTION_KIND,
        "phase": pending["phase"],
        "candidate": candidate.to_json(),
        "previous": None,
        "actor": pending["actor"],
        "startedAt": pending["startedAt"],
        "schemaAfter": schema_after.to_json() if schema_after else None,
        "backupMarkerSha256": pending["backupMarkerSha256"],
    }
    host_state._atomic_write_json(paths.pending_file, payload)


def _require_fresh_committed_authority(paths: HostPaths) -> None:
    if os.path.lexists(paths.state_file) or os.path.lexists(paths.current):
        raise ContractError("fresh bootstrap requires absent current and state")


def _require_commit_observation(paths: HostPaths, candidate: ReleaseIdentity) -> None:
    current = _read_fresh_current(paths, candidate)
    committed = host_state._read_committed_identity(paths)
    if current not in (None, candidate) or committed not in (None, candidate):
        raise ContractError("fresh bootstrap commit observation differs")


def _read_fresh_current(
    paths: HostPaths,
    candidate: ReleaseIdentity,
) -> ReleaseIdentity | None:
    if not os.path.lexists(paths.current):
        return None
    release_name = host_state._require_current_link(paths)
    host_state._require_identity_release(paths, candidate)
    if release_name != candidate.release_name:
        raise ContractError("fresh bootstrap current candidate differs")
    return candidate


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError("fresh bootstrap backup marker identity is invalid")
    return value
