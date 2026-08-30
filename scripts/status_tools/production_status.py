#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable
import urllib.error
import urllib.request

from scripts.backup_tools import backup_artifact


FORMAT_VERSION = 1
SERVICES = ("web", "api", "postgres")
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
INSTANT_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,9})?Z$"
)


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ContractError("Docker 관측 명령을 실행할 수 없습니다.") from error


def default_origin_fetch(url: str) -> int | None:
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=5) as response:
            return response.getcode()
    except urllib.error.HTTPError as error:
        return error.code
    except (OSError, urllib.error.URLError, ValueError):
        return None


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


class ProductionStatusCollector:

    def __init__(
        self,
        *,
        repo_root: Path,
        compose_file: Path,
        project_name: str,
        env_file: Path,
        backup_directory: Path,
        runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = default_runner,
        origin_fetch: Callable[[str], int | None] = default_origin_fetch,
        statvfs: Callable[[Path], os.statvfs_result] = os.statvfs,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
    ) -> None:
        require(
            bool(backup_artifact.PROJECT_PATTERN.fullmatch(project_name)),
            "Compose project 이름이 안전한 형식이 아닙니다.",
        )
        canonical_repo = repo_root.resolve(strict=True)
        canonical_compose = compose_file.resolve(strict=True)
        require(
            canonical_compose == canonical_repo / "compose.prod.yaml",
            "status command의 Compose authority가 canonical file과 다릅니다.",
        )
        try:
            canonical_env = backup_artifact.validate_env_path(
                str(canonical_repo), str(env_file)
            )
            canonical_backup = backup_artifact.validate_backup_directory_read_only(
                str(canonical_repo), str(backup_directory)
            )
        except backup_artifact.ContractError as error:
            raise ContractError(str(error)) from error

        self.repo_root = canonical_repo
        self.compose_file = canonical_compose
        self.project_name = project_name
        self.env_file = canonical_env
        self.backup_directory = canonical_backup
        self.runner = runner
        self.origin_fetch = origin_fetch
        self.statvfs = statvfs
        self.now = now
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            project_name,
            "--env-file",
            str(canonical_env),
            "-f",
            str(canonical_compose),
        ]

    def collect(self) -> dict[str, Any]:
        observed_at = self._now()
        self._validate_compose_config()
        containers = {
            service: self._observe_container(service)
            for service in SERVICES
        }
        service_status = {
            service: self._service_status(containers[service])
            for service in SERVICES
        }
        return {
            "formatVersion": FORMAT_VERSION,
            "observedAt": format_time(observed_at),
            "services": service_status,
            "origin": self._origin_status(containers["web"]),
            "recurring": self._recurring_status(containers["api"]),
            "backup": self._backup_status(observed_at),
            "filesystem": self._filesystem_status(),
        }

    def _validate_compose_config(self) -> None:
        result = self.runner(self.compose + ["config", "--quiet"])
        require(
            result.returncode == 0,
            "canonical production Compose config를 검증할 수 없습니다.",
        )

    def _observe_container(self, service: str) -> dict[str, Any] | None:
        result = self.runner(self.compose + ["ps", "--all", "--quiet", service])
        require(
            result.returncode == 0,
            f"{service} service authority를 관측할 수 없습니다.",
        )
        identifiers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        require(
            len(identifiers) <= 1,
            f"{service} service container가 중복됐습니다.",
        )
        if not identifiers:
            return None
        inspect_result = self.runner(["docker", "inspect", identifiers[0]])
        require(
            inspect_result.returncode == 0,
            f"{service} service container를 관측할 수 없습니다.",
        )
        try:
            payload = json.loads(inspect_result.stdout)
        except json.JSONDecodeError as error:
            raise ContractError(
                f"{service} service inspect contract가 잘못됐습니다."
            ) from error
        require(
            isinstance(payload, list) and len(payload) == 1
            and isinstance(payload[0], dict),
            f"{service} service inspect contract가 잘못됐습니다.",
        )
        container = payload[0]
        self._validate_container_authority(container, service)
        container["_statusContainerId"] = identifiers[0]
        return container

    def _validate_container_authority(
        self, container: dict[str, Any], service: str
    ) -> None:
        labels = ((container.get("Config") or {}).get("Labels") or {})
        require(
            labels.get("com.docker.compose.project") == self.project_name,
            f"{service} container project authority가 다릅니다.",
        )
        require(
            labels.get("com.docker.compose.service") == service,
            f"{service} container service authority가 다릅니다.",
        )
        raw_config_files = labels.get(
            "com.docker.compose.project.config_files", ""
        )
        try:
            config_files = {
                Path(value).resolve()
                for value in raw_config_files.split(",")
                if value
            }
        except (OSError, ValueError) as error:
            raise ContractError(
                f"{service} container Compose authority가 잘못됐습니다."
            ) from error
        require(
            config_files == {self.compose_file},
            f"{service} container Compose authority가 다릅니다.",
        )

        bindings = ((container.get("HostConfig") or {}).get("PortBindings") or {})
        if service == "web":
            require(
                set(bindings) == {"8080/tcp"},
                "web loopback publish authority가 다릅니다.",
            )
            published = bindings.get("8080/tcp") or []
            require(
                len(published) == 1
                and published[0].get("HostIp") == "127.0.0.1"
                and str(published[0].get("HostPort", "")).isdigit(),
                "web loopback publish authority가 다릅니다.",
            )
        else:
            require(
                not bindings,
                f"{service} container가 host port를 publish합니다.",
            )

    def _service_status(
        self, container: dict[str, Any] | None
    ) -> dict[str, Any]:
        if container is None:
            return {
                "state": "MISSING",
                "health": "NONE",
                "restartCount": None,
            }
        state = container.get("State") or {}
        state_value = normalize_state(state.get("Status"))
        health_value = normalize_health((state.get("Health") or {}).get("Status"))
        restart_count = container.get("RestartCount")
        if type(restart_count) is not int or restart_count < 0:
            restart_count = None
        return {
            "state": state_value,
            "health": health_value,
            "restartCount": restart_count,
        }

    def _origin_status(self, container: dict[str, Any] | None) -> dict[str, Any]:
        if container is None or normalize_state(
            (container.get("State") or {}).get("Status")
        ) != "RUNNING":
            return {"reachable": False, "healthzStatus": None}
        published = (
            ((container.get("NetworkSettings") or {}).get("Ports") or {})
            .get("8080/tcp")
            or []
        )
        if not (
            len(published) == 1
            and published[0].get("HostIp") == "127.0.0.1"
            and str(published[0].get("HostPort", "")).isdigit()
            and int(published[0]["HostPort"]) > 0
        ):
            return {"reachable": False, "healthzStatus": None}
        port = published[0]["HostPort"]
        try:
            status = self.origin_fetch(f"http://127.0.0.1:{port}/healthz")
        except Exception:
            status = None
        if type(status) is not int or not 100 <= status <= 599:
            return {"reachable": False, "healthzStatus": None}
        return {"reachable": True, "healthzStatus": status}

    def _recurring_status(
        self, container: dict[str, Any] | None
    ) -> dict[str, Any]:
        unavailable = recurring_unavailable()
        if container is None or normalize_state(
            (container.get("State") or {}).get("Status")
        ) != "RUNNING":
            return unavailable
        identifier = self._container_identifier(container)
        if identifier is None:
            return unavailable
        result = self.runner([
            "docker",
            "exec",
            identifier,
            "java",
            "-cp",
            "/opt/healthcheck",
            "HttpFetch",
            "http://127.0.0.1:8080/actuator/health/operations",
        ])
        if result.returncode != 0 or len(result.stdout) > 1_048_576:
            return unavailable
        try:
            return parse_recurring_response(result.stdout)
        except (ContractError, json.JSONDecodeError, ValueError, TypeError):
            return unavailable

    def _container_identifier(self, container: dict[str, Any]) -> str | None:
        identifier = container.get("_statusContainerId")
        return identifier if type(identifier) is str and identifier else None

    def _backup_status(self, observed_at: dt.datetime) -> dict[str, Any]:
        marker_exists = os.path.lexists(self.backup_directory / "last-success.json")
        empty = {
            "markerState": "MISSING" if not marker_exists else "INVALID",
            "createdAt": None,
            "ageSeconds": None,
            "schemaVersion": None,
            "sizeBytes": None,
            "inventory": {
                "valid": None,
                "invalid": None,
                "incomplete": None,
                "foreign": None,
            },
        }
        try:
            inventory = backup_artifact.inventory(self.backup_directory)
        except (backup_artifact.ContractError, OSError):
            empty["markerState"] = "UNAVAILABLE"
            return empty
        counts = {
            key: len(inventory[key])
            for key in ("valid", "invalid", "incomplete", "foreign")
        }
        empty["inventory"] = counts
        if not marker_exists:
            return empty
        if not inventory.get("lastSuccessValid"):
            return empty
        latest = [item for item in inventory["valid"] if item.get("isLatest")]
        if len(latest) != 1:
            return empty
        item = latest[0]
        try:
            created_at = backup_artifact.parse_created_at(item["createdAt"])
        except (backup_artifact.ContractError, KeyError, TypeError):
            return empty
        age_seconds = int((observed_at - created_at).total_seconds())
        if age_seconds < 0:
            return empty
        empty.update({
            "markerState": "VALID",
            "createdAt": item["createdAt"],
            "ageSeconds": age_seconds,
            "schemaVersion": item["schemaVersion"],
            "sizeBytes": item["sizeBytes"],
        })
        return empty

    def _filesystem_status(self) -> dict[str, Any]:
        unavailable = {
            "state": "UNAVAILABLE",
            "capacityBytes": None,
            "availableBytes": None,
            "usedPercent": None,
        }
        try:
            filesystem = self.statvfs(self.backup_directory)
            fragment_size = filesystem.f_frsize or filesystem.f_bsize
            capacity = fragment_size * filesystem.f_blocks
            available = fragment_size * filesystem.f_bavail
            if capacity <= 0 or available < 0 or available > capacity:
                return unavailable
            used_percent = round((capacity - available) * 100 / capacity, 1)
        except (OSError, AttributeError, ArithmeticError, TypeError, ValueError):
            return unavailable
        return {
            "state": "AVAILABLE",
            "capacityBytes": capacity,
            "availableBytes": available,
            "usedPercent": used_percent,
        }

    def _now(self) -> dt.datetime:
        observed_at = self.now()
        require(
            isinstance(observed_at, dt.datetime)
            and observed_at.tzinfo is not None,
            "관측 시각은 timezone-aware datetime이어야 합니다.",
        )
        return observed_at.astimezone(dt.timezone.utc).replace(microsecond=0)


def parse_recurring_response(raw: str) -> dict[str, Any]:
    status_line, separator, body = raw.partition("\n")
    require(bool(separator), "internal operations HTTP response 형식이 잘못됐습니다.")
    http_status = int(status_line)
    payload = json.loads(body)
    require(isinstance(payload, dict), "internal operations body가 object가 아닙니다.")
    components = payload.get("components")
    require(isinstance(components, dict), "operations components가 없습니다.")
    component = components.get("recurringScheduler")
    require(isinstance(component, dict), "recurringScheduler component가 없습니다.")
    status = component.get("status")
    require(
        status in {"UP", "DOWN", "UNKNOWN"}
        and payload.get("status") == status,
        "recurringScheduler status contract가 잘못됐습니다.",
    )
    require(
        (status == "DOWN" and http_status == 503)
        or (status != "DOWN" and http_status == 200),
        "recurringScheduler HTTP/status contract가 잘못됐습니다.",
    )
    details = component.get("details")
    require(isinstance(details, dict), "recurringScheduler details가 없습니다.")
    require(
        set(RECURRING_DETAIL_KEYS) <= set(details),
        "recurringScheduler detail contract가 누락됐습니다.",
    )
    validate_recurring_details(details)
    validate_recurring_outcome(status, details)
    result = {"reachable": True, "status": status}
    result.update({key: details[key] for key in RECURRING_DETAIL_KEYS})
    return result


def validate_recurring_details(details: dict[str, Any]) -> None:
    require(type(details["enabled"]) is bool, "enabled type이 잘못됐습니다.")
    require_instant(details["processStartedAt"], nullable=False)
    for key in (
        "pollCountSinceStart",
        "lastAdvancedOccurrenceCount",
        "lastPollRuleFailureCount",
        "totalRuleFailureCountSinceStart",
        "consecutivePollExecutionFailures",
    ):
        value = details[key]
        require(
            type(value) is int and value >= 0,
            f"{key} type이 잘못됐습니다.",
        )
    require(
        details["lastPollSucceeded"] is None
        or type(details["lastPollSucceeded"]) is bool,
        "lastPollSucceeded type이 잘못됐습니다.",
    )
    for key in (
        "lastPollStartedAt",
        "lastPollCompletedAt",
        "lastPollExecutionFailureAt",
        "lastRuleFailureAt",
    ):
        require_instant(details[key], nullable=True)


def validate_recurring_outcome(status: str, details: dict[str, Any]) -> None:
    if status == "UP":
        require(
            details["lastPollSucceeded"] is True,
            "UP recurringScheduler의 last poll outcome이 잘못됐습니다.",
        )
    elif status == "DOWN":
        require(
            details["lastPollSucceeded"] is False,
            "DOWN recurringScheduler의 last poll outcome이 잘못됐습니다.",
        )


def require_instant(value: Any, *, nullable: bool) -> None:
    if nullable and value is None:
        return
    require(
        type(value) is str and bool(INSTANT_PATTERN.fullmatch(value)),
        "operational timestamp contract가 잘못됐습니다.",
    )


def recurring_unavailable() -> dict[str, Any]:
    result: dict[str, Any] = {"reachable": False, "status": "UNREACHABLE"}
    result.update({key: None for key in RECURRING_DETAIL_KEYS})
    return result


def normalize_state(value: Any) -> str:
    if type(value) is not str:
        return "UNKNOWN"
    normalized = value.upper()
    return normalized if normalized in {
        "CREATED", "RUNNING", "PAUSED", "RESTARTING", "REMOVING",
        "EXITED", "DEAD",
    } else "UNKNOWN"


def normalize_health(value: Any) -> str:
    if value is None:
        return "NONE"
    if type(value) is not str:
        return "UNKNOWN"
    normalized = value.upper()
    return normalized if normalized in {
        "STARTING", "HEALTHY", "UNHEALTHY",
    } else "UNKNOWN"


def format_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="our-ledger read-only production status snapshot"
    )
    result.add_argument("--project-name", required=True)
    result.add_argument("--env-file", required=True)
    result.add_argument("--backup-dir", required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    collector = ProductionStatusCollector(
        repo_root=repo_root,
        compose_file=repo_root / "compose.prod.yaml",
        project_name=args.project_name,
        env_file=Path(args.env_file),
        backup_directory=Path(args.backup_dir),
    )
    print(json.dumps(collector.collect(), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except ContractError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    except Exception as error:
        print("status snapshot을 생성할 수 없습니다.", file=sys.stderr)
        raise SystemExit(1) from error
