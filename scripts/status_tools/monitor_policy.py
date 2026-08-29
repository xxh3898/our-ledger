#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import decimal
import json
import re
import sys
from typing import Any


FORMAT_VERSION = 1
STATE_FORMAT_VERSION = 2
SERVICE_TARGETS = ("web", "api", "postgres", "recurring")
COMPOSE_SERVICES = SERVICE_TARGETS[:3]
SEVERITIES = ("OK", "WARN", "CRITICAL")
SIGNAL_CODES = frozenset({
    "SERVICE_PENDING",
    "SERVICE_DOWN",
    "ORIGIN_PENDING",
    "ORIGIN_DOWN",
    "RECURRING_STARTING",
    "RECURRING_NOT_RUNNING",
    "RECURRING_STALE",
    "RECURRING_EXECUTION_FAILED",
    "RECURRING_RULE_FAILURE",
    "BACKUP_MISSING",
    "BACKUP_INVALID",
    "BACKUP_UNAVAILABLE",
    "BACKUP_STALE",
    "BACKUP_INVENTORY_WARNING",
    "FILESYSTEM_UNAVAILABLE",
    "DISK_USAGE_WARNING",
    "DISK_USAGE_CRITICAL",
    "STATE_INVALID",
    "STATUS_UNAVAILABLE",
})
SERVICE_STATES = frozenset({
    "MISSING",
    "CREATED",
    "RUNNING",
    "PAUSED",
    "RESTARTING",
    "REMOVING",
    "EXITED",
    "DEAD",
    "UNKNOWN",
})
SERVICE_HEALTH = frozenset({
    "HEALTHY", "UNHEALTHY", "STARTING", "NONE", "UNKNOWN",
})
RECURRING_DETAIL_KEYS = (
    "enabled",
    "processStartedAt",
    "pollCountSinceStart",
    "lastPollStartedAt",
    "lastPollCompletedAt",
    "lastPollSucceeded",
    "lastAdvancedOccurrenceCount",
    "lastPollRuleFailureCount",
    "totalRuleFailureCountSinceStart",
    "consecutivePollExecutionFailures",
    "lastPollExecutionFailureAt",
    "lastRuleFailureAt",
)
STATE_KEYS = frozenset({
    "formatVersion",
    "lastObservedAt",
    "serviceFailureStreaks",
    "originFailureStreak",
    "lastRecurringPollCompletedAtSeen",
    "recurringRuleFailureStreak",
    "lastOverallStatus",
    "homeOpsDisk",
})
HOMEOPS_DISK_STATE_KEYS = frozenset({
    "episodeSequence",
    "activeEpisodeKey",
    "pendingSignal",
})
HOMEOPS_DISK_SIGNAL_KEYS = frozenset({
    "eventKey",
    "episodeKey",
    "project",
    "signalType",
    "status",
    "observedAt",
    "availablePercent",
    "thresholdPercent",
})
INSTANT_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,9})?Z$"
)
MAX_STREAK = 1_000_000
MAX_EPISODE_SEQUENCE = 1_000_000
RECURRING_GRACE_SECONDS = 5 * 60
RECURRING_STALE_SECONDS = 5 * 60
BACKUP_STALE_SECONDS = 7 * 60 * 60
HOMEOPS_PROJECT = "our-ledger"
HOMEOPS_DISK_THRESHOLD_PERCENT = 20
HOMEOPS_DISK_EPISODE_PATTERN = re.compile(
    r"^our-ledger:disk-low:([1-9][0-9]{0,6})$"
)


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _exact_object(value: Any, keys: set[str] | frozenset[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label}는 JSON object여야 합니다.")
    require(set(value) == set(keys), f"{label} field가 exact contract와 다릅니다.")
    return value


def _bounded_count(value: Any, label: str) -> int:
    require(
        type(value) is int and 0 <= value <= MAX_STREAK,
        f"{label} count가 잘못됐습니다.",
    )
    return value


def parse_instant(value: Any, label: str, *, nullable: bool = False) -> dt.datetime | None:
    if nullable and value is None:
        return None
    require(
        type(value) is str and bool(INSTANT_PATTERN.fullmatch(value)),
        f"{label} timestamp 형식이 잘못됐습니다.",
    )
    try:
        parsed = dt.datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ContractError(f"{label} timestamp가 잘못됐습니다.") from error
    return parsed.astimezone(dt.timezone.utc)


def format_instant(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state() -> dict[str, Any]:
    return {
        "formatVersion": STATE_FORMAT_VERSION,
        "lastObservedAt": None,
        "serviceFailureStreaks": {target: 0 for target in SERVICE_TARGETS},
        "originFailureStreak": 0,
        "lastRecurringPollCompletedAtSeen": None,
        "recurringRuleFailureStreak": 0,
        "lastOverallStatus": "OK",
        "homeOpsDisk": {
            "episodeSequence": 0,
            "activeEpisodeKey": None,
            "pendingSignal": None,
        },
    }


def _episode_sequence(value: Any, label: str, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    require(type(value) is str, f"{label} 형식이 잘못됐습니다.")
    matched = HOMEOPS_DISK_EPISODE_PATTERN.fullmatch(value)
    require(matched is not None, f"{label} 형식이 잘못됐습니다.")
    sequence = int(matched.group(1))
    require(sequence <= MAX_EPISODE_SEQUENCE, f"{label} sequence가 제한을 초과했습니다.")
    return sequence


def _percent(value: Any, label: str) -> int | float:
    require(
        not isinstance(value, bool) and isinstance(value, (int, float)),
        f"{label} type이 잘못됐습니다.",
    )
    number = decimal.Decimal(str(value))
    require(
        number.is_finite()
        and decimal.Decimal("0") <= number <= decimal.Decimal("100")
        and number.as_tuple().exponent >= -2,
        f"{label} 값이 잘못됐습니다.",
    )
    return value


def validate_homeops_disk_signal(value: Any) -> dict[str, Any]:
    signal = _exact_object(value, HOMEOPS_DISK_SIGNAL_KEYS, "HomeOps disk signal")
    require(signal["project"] == HOMEOPS_PROJECT, "HomeOps signal project가 잘못됐습니다.")
    require(signal["signalType"] == "DISK_LOW", "HomeOps signalType이 잘못됐습니다.")
    require(signal["status"] in {"ALERT", "RECOVERED"}, "HomeOps signal status가 잘못됐습니다.")
    parse_instant(signal["observedAt"], "HomeOps observedAt")
    sequence = _episode_sequence(signal["episodeKey"], "HomeOps episodeKey")
    assert sequence is not None
    suffix = "alert" if signal["status"] == "ALERT" else "recovered"
    require(
        signal["eventKey"] == f"{signal['episodeKey']}:{suffix}",
        "HomeOps eventKey가 lifecycle과 일치하지 않습니다.",
    )
    _percent(signal["availablePercent"], "HomeOps availablePercent")
    require(
        type(signal["thresholdPercent"]) is int
        and signal["thresholdPercent"] == HOMEOPS_DISK_THRESHOLD_PERCENT,
        "HomeOps thresholdPercent가 잘못됐습니다.",
    )
    return json.loads(json.dumps(signal))


def validate_state(value: Any) -> dict[str, Any]:
    state = _exact_object(value, STATE_KEYS, "monitor state")
    require(
        state["formatVersion"] == STATE_FORMAT_VERSION,
        "monitor state formatVersion이 잘못됐습니다.",
    )
    parse_instant(state["lastObservedAt"], "lastObservedAt", nullable=True)
    streaks = _exact_object(
        state["serviceFailureStreaks"], set(SERVICE_TARGETS), "serviceFailureStreaks"
    )
    for target in SERVICE_TARGETS:
        _bounded_count(streaks[target], f"{target} failure streak")
    _bounded_count(state["originFailureStreak"], "origin failure streak")
    parse_instant(
        state["lastRecurringPollCompletedAtSeen"],
        "lastRecurringPollCompletedAtSeen",
        nullable=True,
    )
    _bounded_count(
        state["recurringRuleFailureStreak"], "recurring rule failure streak"
    )
    require(
        state["lastOverallStatus"] in SEVERITIES,
        "lastOverallStatus가 잘못됐습니다.",
    )
    homeops = _exact_object(
        state["homeOpsDisk"], HOMEOPS_DISK_STATE_KEYS, "homeOpsDisk"
    )
    sequence = homeops["episodeSequence"]
    require(
        type(sequence) is int and 0 <= sequence <= MAX_EPISODE_SEQUENCE,
        "homeOpsDisk episodeSequence가 잘못됐습니다.",
    )
    active_sequence = _episode_sequence(
        homeops["activeEpisodeKey"], "homeOpsDisk activeEpisodeKey", nullable=True
    )
    require(
        active_sequence is None or active_sequence <= sequence,
        "homeOpsDisk active episode가 sequence보다 미래입니다.",
    )
    pending = homeops["pendingSignal"]
    if pending is not None:
        pending = validate_homeops_disk_signal(pending)
        pending_sequence = _episode_sequence(
            pending["episodeKey"], "HomeOps pending episodeKey"
        )
        assert pending_sequence is not None
        require(
            pending_sequence == sequence,
            "HomeOps pending episode가 current sequence와 다릅니다.",
        )
        if pending["status"] == "ALERT":
            require(
                active_sequence is None,
                "pending ALERT 전에 active episode가 없어야 합니다.",
            )
        else:
            require(
                homeops["activeEpisodeKey"] == pending["episodeKey"],
                "pending RECOVERED는 active episode와 일치해야 합니다.",
            )
    return json.loads(json.dumps(state))


def validate_snapshot(value: Any) -> dict[str, Any]:
    snapshot = _exact_object(
        value,
        {"formatVersion", "observedAt", "services", "origin", "recurring", "backup", "filesystem"},
        "production status snapshot",
    )
    require(snapshot["formatVersion"] == FORMAT_VERSION, "snapshot formatVersion이 잘못됐습니다.")
    observed_at = parse_instant(snapshot["observedAt"], "observedAt")
    assert observed_at is not None

    services = _exact_object(snapshot["services"], set(COMPOSE_SERVICES), "services")
    for name in COMPOSE_SERVICES:
        service = _exact_object(
            services[name], {"state", "health", "restartCount"}, f"{name} service"
        )
        require(service["state"] in SERVICE_STATES, f"{name} state가 잘못됐습니다.")
        require(service["health"] in SERVICE_HEALTH, f"{name} health가 잘못됐습니다.")
        restart_count = service["restartCount"]
        require(
            restart_count is None or (type(restart_count) is int and restart_count >= 0),
            f"{name} restartCount가 잘못됐습니다.",
        )

    origin = _exact_object(snapshot["origin"], {"reachable", "healthzStatus"}, "origin")
    require(type(origin["reachable"]) is bool, "origin reachable type이 잘못됐습니다.")
    require(
        origin["healthzStatus"] is None
        or (type(origin["healthzStatus"]) is int and 100 <= origin["healthzStatus"] <= 599),
        "origin healthzStatus가 잘못됐습니다.",
    )

    recurring = _exact_object(
        snapshot["recurring"],
        {"reachable", "status", *RECURRING_DETAIL_KEYS},
        "recurring",
    )
    require(type(recurring["reachable"]) is bool, "recurring reachable type이 잘못됐습니다.")
    if not recurring["reachable"]:
        require(recurring["status"] == "UNREACHABLE", "unreachable recurring status가 잘못됐습니다.")
        require(
            all(recurring[key] is None for key in RECURRING_DETAIL_KEYS),
            "unreachable recurring detail은 null이어야 합니다.",
        )
    else:
        require(recurring["status"] in {"UP", "DOWN", "UNKNOWN"}, "recurring status가 잘못됐습니다.")
        require(type(recurring["enabled"]) is bool, "recurring enabled type이 잘못됐습니다.")
        process_started_at = parse_instant(recurring["processStartedAt"], "processStartedAt")
        assert process_started_at is not None
        require(process_started_at <= observed_at, "processStartedAt이 observedAt보다 미래입니다.")
        for key in (
            "pollCountSinceStart",
            "lastAdvancedOccurrenceCount",
            "lastPollRuleFailureCount",
            "totalRuleFailureCountSinceStart",
            "consecutivePollExecutionFailures",
        ):
            _bounded_count(recurring[key], key)
        require(
            recurring["lastPollSucceeded"] is None
            or type(recurring["lastPollSucceeded"]) is bool,
            "lastPollSucceeded type이 잘못됐습니다.",
        )
        parsed_times: dict[str, dt.datetime | None] = {}
        for key in (
            "lastPollStartedAt",
            "lastPollCompletedAt",
            "lastPollExecutionFailureAt",
            "lastRuleFailureAt",
        ):
            parsed_times[key] = parse_instant(recurring[key], key, nullable=True)
            require(
                parsed_times[key] is None or parsed_times[key] <= observed_at,
                f"{key}이 observedAt보다 미래입니다.",
            )
        poll_count = recurring["pollCountSinceStart"]
        if recurring["lastPollCompletedAt"] is None:
            require(
                recurring["status"] == "UNKNOWN"
                and recurring["lastPollSucceeded"] is None,
                "in-progress recurring outcome이 잘못됐습니다.",
            )
            if poll_count == 0:
                require(
                    recurring["lastPollStartedAt"] is None,
                    "poll 0 recurring start timestamp가 잘못됐습니다.",
                )
            else:
                require(
                    recurring["lastPollStartedAt"] is not None,
                    "in-progress recurring start timestamp가 없습니다.",
                )
        else:
            require(
                poll_count > 0 and type(recurring["lastPollSucceeded"]) is bool,
                "completed recurring poll outcome이 누락됐습니다.",
            )
        if recurring["status"] == "UP":
            require(recurring["lastPollSucceeded"] is True, "UP recurring outcome이 잘못됐습니다.")
        if recurring["status"] == "DOWN":
            require(recurring["lastPollSucceeded"] is False, "DOWN recurring outcome이 잘못됐습니다.")

    backup = _exact_object(
        snapshot["backup"],
        {"markerState", "createdAt", "ageSeconds", "schemaVersion", "sizeBytes", "inventory"},
        "backup",
    )
    require(
        backup["markerState"] in {"VALID", "MISSING", "INVALID", "UNAVAILABLE"},
        "backup markerState가 잘못됐습니다.",
    )
    inventory = _exact_object(
        backup["inventory"], {"valid", "invalid", "incomplete", "foreign"}, "backup inventory"
    )
    for key, count in inventory.items():
        require(
            count is None or (type(count) is int and count >= 0),
            f"backup inventory {key} count가 잘못됐습니다.",
        )
    if backup["markerState"] == "VALID":
        created_at = parse_instant(backup["createdAt"], "backup createdAt")
        assert created_at is not None
        require(created_at <= observed_at, "backup createdAt이 observedAt보다 미래입니다.")
        require(type(backup["ageSeconds"]) is int and backup["ageSeconds"] >= 0, "backup ageSeconds가 잘못됐습니다.")
        require(type(backup["schemaVersion"]) is str and bool(backup["schemaVersion"]), "backup schemaVersion이 잘못됐습니다.")
        require(type(backup["sizeBytes"]) is int and backup["sizeBytes"] > 0, "backup sizeBytes가 잘못됐습니다.")
        require(all(type(count) is int for count in inventory.values()), "valid backup inventory가 불완전합니다.")
    else:
        require(
            all(backup[key] is None for key in ("createdAt", "ageSeconds", "schemaVersion", "sizeBytes")),
            "invalid backup detail은 null이어야 합니다.",
        )

    filesystem = _exact_object(
        snapshot["filesystem"],
        {"state", "capacityBytes", "availableBytes", "usedPercent"},
        "filesystem",
    )
    require(filesystem["state"] in {"AVAILABLE", "UNAVAILABLE"}, "filesystem state가 잘못됐습니다.")
    if filesystem["state"] == "AVAILABLE":
        require(type(filesystem["capacityBytes"]) is int and filesystem["capacityBytes"] > 0, "filesystem capacityBytes가 잘못됐습니다.")
        require(type(filesystem["availableBytes"]) is int and 0 <= filesystem["availableBytes"] <= filesystem["capacityBytes"], "filesystem availableBytes가 잘못됐습니다.")
        require(
            type(filesystem["usedPercent"]) in {int, float}
            and not isinstance(filesystem["usedPercent"], bool)
            and 0 <= filesystem["usedPercent"] <= 100,
            "filesystem usedPercent가 잘못됐습니다.",
        )
    else:
        require(
            all(filesystem[key] is None for key in ("capacityBytes", "availableBytes", "usedPercent")),
            "unavailable filesystem detail은 null이어야 합니다.",
        )
    return snapshot


def _increment(value: int) -> int:
    return min(value + 1, MAX_STREAK)


def _signal(code: str, severity: str, *, target: str | None = None) -> dict[str, str]:
    require(code in SIGNAL_CODES, "signal code allowlist가 잘못됐습니다.")
    require(severity in {"WARN", "CRITICAL"}, "signal severity가 잘못됐습니다.")
    result = {"code": code, "severity": severity}
    if target is not None:
        require(target in SERVICE_TARGETS, "signal target allowlist가 잘못됐습니다.")
        result["target"] = target
    return result


def _overall_status(signals: list[dict[str, str]]) -> str:
    if any(signal["severity"] == "CRITICAL" for signal in signals):
        return "CRITICAL"
    if signals:
        return "WARN"
    return "OK"


def evaluate(
    snapshot_value: Any,
    previous_state_value: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = validate_snapshot(snapshot_value)
    previous = validate_state(
        default_state() if previous_state_value is None else previous_state_value
    )
    observed_at = parse_instant(snapshot["observedAt"], "observedAt")
    previous_observed_at = parse_instant(
        previous["lastObservedAt"], "lastObservedAt", nullable=True
    )
    assert observed_at is not None
    require(
        previous_observed_at is None or observed_at > previous_observed_at,
        "snapshot observedAt은 previous state보다 새로워야 합니다.",
    )

    next_state = validate_state(previous)
    signals: list[dict[str, str]] = []

    service_failures = {
        name: (
            snapshot["services"][name]["state"] != "RUNNING"
            or snapshot["services"][name]["health"] != "HEALTHY"
        )
        for name in COMPOSE_SERVICES
    }
    service_failures["recurring"] = (
        snapshot["recurring"]["reachable"] is not True
        or snapshot["recurring"]["status"] == "UNREACHABLE"
    )
    for target in SERVICE_TARGETS:
        if service_failures[target]:
            streak = _increment(previous["serviceFailureStreaks"][target])
            next_state["serviceFailureStreaks"][target] = streak
            signals.append(
                _signal(
                    "SERVICE_PENDING" if streak == 1 else "SERVICE_DOWN",
                    "WARN" if streak == 1 else "CRITICAL",
                    target=target,
                )
            )
        else:
            next_state["serviceFailureStreaks"][target] = 0

    origin_failed = (
        snapshot["origin"]["reachable"] is not True
        or snapshot["origin"]["healthzStatus"] != 200
    )
    if origin_failed:
        origin_streak = _increment(previous["originFailureStreak"])
        next_state["originFailureStreak"] = origin_streak
        signals.append(
            _signal(
                "ORIGIN_PENDING" if origin_streak == 1 else "ORIGIN_DOWN",
                "WARN" if origin_streak == 1 else "CRITICAL",
            )
        )
    else:
        next_state["originFailureStreak"] = 0

    recurring = snapshot["recurring"]
    if recurring["reachable"]:
        process_started_at = parse_instant(recurring["processStartedAt"], "processStartedAt")
        last_completed = parse_instant(
            recurring["lastPollCompletedAt"], "lastPollCompletedAt", nullable=True
        )
        assert process_started_at is not None
        if recurring["enabled"] is not True:
            signals.append(_signal("RECURRING_NOT_RUNNING", "CRITICAL"))
        elif recurring["status"] == "DOWN" or recurring["lastPollSucceeded"] is False:
            signals.append(_signal("RECURRING_EXECUTION_FAILED", "CRITICAL"))
        elif last_completed is None:
            process_age = (observed_at - process_started_at).total_seconds()
            if process_age < RECURRING_GRACE_SECONDS:
                signals.append(_signal("RECURRING_STARTING", "WARN"))
            else:
                signals.append(_signal("RECURRING_NOT_RUNNING", "CRITICAL"))
        else:
            require(last_completed is not None, "recurring completed poll timestamp가 없습니다.")
            if (observed_at - last_completed).total_seconds() > RECURRING_STALE_SECONDS:
                signals.append(_signal("RECURRING_STALE", "CRITICAL"))

        previous_poll = parse_instant(
            previous["lastRecurringPollCompletedAtSeen"],
            "lastRecurringPollCompletedAtSeen",
            nullable=True,
        )
        if last_completed is None:
            next_state["lastRecurringPollCompletedAtSeen"] = None
            next_state["recurringRuleFailureStreak"] = 0
        elif last_completed is not None:
            require(
                previous_poll is None or last_completed >= previous_poll,
                "recurring completed poll timestamp가 역행했습니다.",
            )
            if previous_poll is None or last_completed > previous_poll:
                next_state["lastRecurringPollCompletedAtSeen"] = recurring["lastPollCompletedAt"]
                if recurring["lastPollRuleFailureCount"] > 0:
                    next_state["recurringRuleFailureStreak"] = _increment(
                        previous["recurringRuleFailureStreak"]
                    )
                else:
                    next_state["recurringRuleFailureStreak"] = 0
            if next_state["recurringRuleFailureStreak"] > 0:
                signals.append(
                    _signal(
                        "RECURRING_RULE_FAILURE",
                        "CRITICAL"
                        if next_state["recurringRuleFailureStreak"] >= 3
                        else "WARN",
                    )
                )

    backup = snapshot["backup"]
    marker_signal = {
        "MISSING": "BACKUP_MISSING",
        "INVALID": "BACKUP_INVALID",
        "UNAVAILABLE": "BACKUP_UNAVAILABLE",
    }.get(backup["markerState"])
    if marker_signal is not None:
        signals.append(_signal(marker_signal, "CRITICAL"))
    else:
        if backup["ageSeconds"] >= BACKUP_STALE_SECONDS:
            signals.append(_signal("BACKUP_STALE", "CRITICAL"))
        inventory = backup["inventory"]
        if inventory["invalid"] > 0 or inventory["incomplete"] > 0:
            signals.append(_signal("BACKUP_INVENTORY_WARNING", "WARN"))

    filesystem = snapshot["filesystem"]
    if filesystem["state"] == "UNAVAILABLE":
        signals.append(_signal("FILESYSTEM_UNAVAILABLE", "CRITICAL"))
    elif filesystem["usedPercent"] >= 90:
        signals.append(_signal("DISK_USAGE_CRITICAL", "CRITICAL"))
    elif filesystem["usedPercent"] >= 80:
        signals.append(_signal("DISK_USAGE_WARNING", "WARN"))

    overall = _overall_status(signals)
    next_state["lastObservedAt"] = snapshot["observedAt"]
    next_state["lastOverallStatus"] = overall
    result = {
        "formatVersion": FORMAT_VERSION,
        "observedAt": snapshot["observedAt"],
        "status": overall,
        "signals": signals,
    }
    validate_state(next_state)
    return result, next_state


def failure_result(observed_at: str, code: str) -> dict[str, Any]:
    parse_instant(observed_at, "observedAt")
    require(code in {"STATE_INVALID", "STATUS_UNAVAILABLE"}, "failure signal code가 잘못됐습니다.")
    return {
        "formatVersion": FORMAT_VERSION,
        "observedAt": observed_at,
        "status": "CRITICAL",
        "signals": [_signal(code, "CRITICAL")],
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        payload = _exact_object(payload, {"snapshot", "previousState"}, "policy input")
        result, next_state = evaluate(payload["snapshot"], payload["previousState"])
        print(
            json.dumps(
                {"result": result, "nextState": next_state},
                ensure_ascii=True,
                sort_keys=True,
            )
        )
    except (ContractError, json.JSONDecodeError, UnicodeError, TypeError, ValueError) as error:
        print("monitor policy input contract를 평가할 수 없습니다.", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
