#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path, PurePath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

from scripts.status_tools import monitor_policy


STATE_FILENAME = "monitor-state.json"
LOCK_FILENAME = ".our-ledger-monitor.lock"
HEARTBEAT_CONFIG_KEY = "STATUS_HEARTBEAT_URL"
MAX_PRIVATE_FILE_BYTES = 65_536
MAX_STATUS_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 65_536
MAX_HEARTBEAT_URL_BYTES = 4_096
MAX_HEARTBEAT_MESSAGE_BYTES = 512
PUSH_PATH_PATTERN = re.compile(r"^/api/push/[A-Za-z0-9_-]+/?$")


class ContractError(RuntimeError):
    pass


class LockBusyError(ContractError):
    pass


class StatusUnavailableError(ContractError):
    pass


class DeliveryError(ContractError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _is_within(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


def _raw_path(value: str, label: str) -> Path:
    require(bool(value), f"{label} path가 비어 있습니다.")
    require(not _has_control(value), f"{label} path에 control 문자를 사용할 수 없습니다.")
    candidate = Path(value)
    require(candidate.is_absolute(), f"{label} path는 absolute path여야 합니다.")
    require(".." not in PurePath(value).parts, f"{label} path에 '..'를 사용할 수 없습니다.")
    return candidate


def _private_info(path: Path, label: str, *, directory: bool) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as error:
        raise ContractError(f"{label} metadata를 확인할 수 없습니다.") from error
    require(not stat.S_ISLNK(info.st_mode), f"{label}는 symlink일 수 없습니다.")
    require(
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
        f"{label} type이 잘못됐습니다.",
    )
    require(info.st_uid == os.geteuid(), f"{label} owner가 현재 실행 사용자와 다릅니다.")
    require(
        stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
        f"{label} mode가 owner-only contract와 다릅니다.",
    )
    return info


def _canonical_external(
    repo_root: Path,
    value: str,
    label: str,
    *,
    directory: bool,
) -> Path:
    candidate = _raw_path(value, label)
    require(candidate.exists(), f"{label} path가 존재하지 않습니다.")
    _private_info(candidate, label, directory=directory)
    try:
        canonical = candidate.resolve(strict=True)
        canonical_repo = repo_root.resolve(strict=True)
    except OSError as error:
        raise ContractError(f"{label} path를 canonicalize할 수 없습니다.") from error
    require(not _is_within(canonical, canonical_repo), f"{label}는 repository 밖에 있어야 합니다.")
    return canonical


def validate_state_directory(repo_root: Path, value: str) -> Path:
    state_directory = _canonical_external(
        repo_root, value, "monitor state directory", directory=True
    )
    home = Path.home().resolve()
    protected = {
        Path("/").resolve(),
        home,
        repo_root.resolve(),
        repo_root.resolve().parent,
    }
    for candidate in (
        home / "Server",
        home / "Server" / "apps",
        home / "Server" / "data",
        home / "Server" / "backups",
    ):
        if candidate.exists():
            protected.add(candidate.resolve())
    require(
        state_directory not in protected,
        "monitor state directory가 broad 또는 protected root와 같습니다.",
    )
    for candidate in (
        Path("/var/lib/docker"),
        Path("/var/lib/containers"),
        Path("/var/lib/postgresql"),
        home / "Library" / "Containers" / "com.docker.docker",
    ):
        if candidate.exists():
            require(
                not _is_within(state_directory, candidate.resolve()),
                "monitor state directory로 Docker/PostgreSQL data path를 사용할 수 없습니다.",
            )
    return state_directory


def validate_heartbeat_config(repo_root: Path, value: str) -> Path:
    return _canonical_external(
        repo_root, value, "monitor heartbeat config", directory=False
    )


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_private_file(path: Path, label: str) -> bytes:
    before = _private_info(path, label, directory=False)
    require(before.st_size <= MAX_PRIVATE_FILE_BYTES, f"{label} size가 제한을 초과했습니다.")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ContractError(f"{label}을 열 수 없습니다.") from error
    try:
        after = os.fstat(descriptor)
        _private_info_from_stat(after, label, directory=False)
        require(
            (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
            f"{label}이 open 중 교체됐습니다.",
        )
        chunks: list[bytes] = []
        remaining = MAX_PRIVATE_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        require(len(content) <= MAX_PRIVATE_FILE_BYTES, f"{label} size가 제한을 초과했습니다.")
        return content
    finally:
        os.close(descriptor)


def _private_info_from_stat(
    info: os.stat_result, label: str, *, directory: bool
) -> os.stat_result:
    require(
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
        f"{label} type이 잘못됐습니다.",
    )
    require(info.st_uid == os.geteuid(), f"{label} owner가 현재 실행 사용자와 다릅니다.")
    require(
        stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
        f"{label} mode가 owner-only contract와 다릅니다.",
    )
    return info


class MonitorStateStore:

    def __init__(self, directory: Path) -> None:
        _private_info(directory, "monitor state directory", directory=True)
        self.directory = directory
        self.path = directory / STATE_FILENAME

    def load(self) -> dict[str, Any]:
        if not os.path.lexists(self.path):
            return monitor_policy.default_state()
        content = _read_private_file(self.path, "monitor state file")
        require(bool(content), "monitor state file이 비어 있습니다.")
        try:
            value = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContractError("monitor state file contract가 잘못됐습니다.") from error
        try:
            return monitor_policy.validate_state(value)
        except monitor_policy.ContractError as error:
            raise ContractError("monitor state file contract가 잘못됐습니다.") from error

    def save(self, state: dict[str, Any]) -> None:
        try:
            validated = monitor_policy.validate_state(state)
        except monitor_policy.ContractError as error:
            raise ContractError("monitor state update contract가 잘못됐습니다.") from error
        content = (
            json.dumps(validated, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        require(len(content) <= MAX_PRIVATE_FILE_BYTES, "monitor state update size가 제한을 초과했습니다.")
        if os.path.lexists(self.path):
            _private_info(self.path, "monitor state file", directory=False)

        descriptor, raw_path = tempfile.mkstemp(
            prefix=".monitor-state.", dir=self.directory
        )
        temporary = Path(raw_path)
        replaced = False
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                require(written > 0, "monitor state temp write가 진행되지 않았습니다.")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            if os.path.lexists(self.path):
                _private_info(self.path, "monitor state file", directory=False)
            os.replace(temporary, self.path)
            replaced = True
            _fsync_directory(self.directory)
            _private_info(self.path, "monitor state file", directory=False)
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            if not replaced and temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
            raise


class MonitorLock:

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / LOCK_FILENAME
        self.descriptor: int | None = None

    def __enter__(self) -> MonitorLock:
        existed = os.path.lexists(self.path)
        if existed:
            _private_info(self.path, "monitor lock file", directory=False)
        flags = (
            os.O_CREAT
            | os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except OSError as error:
            raise ContractError("monitor lock file을 열 수 없습니다.") from error
        try:
            if not existed:
                os.fchmod(descriptor, 0o600)
                _fsync_directory(self.directory)
            _private_info_from_stat(
                os.fstat(descriptor), "monitor lock file", directory=False
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise LockBusyError("monitor 실행이 이미 진행 중입니다.") from error
        except BaseException:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self.descriptor is not None:
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            finally:
                os.close(self.descriptor)
                self.descriptor = None


def validate_heartbeat_url(value: str) -> str:
    require(bool(value), "heartbeat URL이 비어 있습니다.")
    require(
        len(value.encode("utf-8")) <= MAX_HEARTBEAT_URL_BYTES,
        "heartbeat URL size가 제한을 초과했습니다.",
    )
    require(not _has_control(value) and not any(character.isspace() for character in value), "heartbeat URL 형식이 잘못됐습니다.")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ContractError("heartbeat URL 형식이 잘못됐습니다.") from error
    require(parsed.scheme in {"http", "https"}, "heartbeat URL scheme이 잘못됐습니다.")
    require(parsed.hostname is not None and bool(parsed.hostname), "heartbeat URL host가 없습니다.")
    require(parsed.username is None and parsed.password is None, "heartbeat URL에 user info를 사용할 수 없습니다.")
    require(not parsed.fragment, "heartbeat URL에 fragment를 사용할 수 없습니다.")
    require(bool(PUSH_PATH_PATTERN.fullmatch(parsed.path)), "heartbeat URL path가 잘못됐습니다.")
    if parsed.scheme == "http":
        require(
            parsed.hostname in {"127.0.0.1", "localhost", "::1"},
            "HTTP heartbeat URL은 loopback만 허용합니다.",
        )
    if port is not None:
        require(1 <= port <= 65535, "heartbeat URL port가 잘못됐습니다.")
    try:
        query = urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=16,
        )
    except ValueError as error:
        raise ContractError("heartbeat URL query가 잘못됐습니다.") from error
    require(len(query) <= 16, "heartbeat URL query field가 너무 많습니다.")
    return value


def load_heartbeat_url(config_path: Path) -> str:
    content = _read_private_file(config_path, "monitor heartbeat config")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("monitor heartbeat config encoding이 잘못됐습니다.") from error
    lines = text.splitlines()
    require(len(lines) == 1, "monitor heartbeat config는 exact key 하나만 허용합니다.")
    prefix = f"{HEARTBEAT_CONFIG_KEY}="
    require(lines[0].startswith(prefix), "monitor heartbeat config key가 잘못됐습니다.")
    require(lines[0].count("=") >= 1, "monitor heartbeat config 형식이 잘못됐습니다.")
    return validate_heartbeat_url(lines[0][len(prefix):])


def heartbeat_message(result: dict[str, Any]) -> str:
    status = result.get("status")
    require(status in monitor_policy.SEVERITIES, "policy result status가 잘못됐습니다.")
    signals = result.get("signals")
    require(isinstance(signals, list), "policy result signals가 잘못됐습니다.")
    parts: list[str] = []
    for signal in signals:
        require(isinstance(signal, dict), "policy signal이 잘못됐습니다.")
        code = signal.get("code")
        target = signal.get("target")
        require(code in monitor_policy.SIGNAL_CODES, "policy signal code가 잘못됐습니다.")
        require(target is None or target in monitor_policy.SERVICE_TARGETS, "policy signal target이 잘못됐습니다.")
        parts.append(code if target is None else f"{code}:{target}")
    message = "OK" if not parts else f"{status} " + ",".join(parts)
    require(
        len(message.encode("utf-8")) <= MAX_HEARTBEAT_MESSAGE_BYTES,
        "heartbeat message size가 제한을 초과했습니다.",
    )
    return message


def _delivery_url(base_url: str, result: dict[str, Any]) -> str:
    validate_heartbeat_url(base_url)
    parsed = urllib.parse.urlsplit(base_url)
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(
            parsed.query, keep_blank_values=True, max_num_fields=16
        )
        if key not in {"status", "msg", "ping"}
    ]
    query.extend([
        ("status", "down" if result["status"] == "CRITICAL" else "up"),
        ("msg", heartbeat_message(result)),
        ("ping", ""),
    ])
    delivery_url = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))
    require(
        len(delivery_url.encode("utf-8")) <= MAX_HEARTBEAT_URL_BYTES,
        "heartbeat delivery URL size가 제한을 초과했습니다.",
    )
    return delivery_url


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


def send_heartbeat(base_url: str, result: dict[str, Any]) -> None:
    try:
        request = urllib.request.Request(
            _delivery_url(base_url, result),
            headers={"User-Agent": "our-ledger-monitor/1"},
            method="GET",
        )
        opener = urllib.request.build_opener(NoRedirectHandler())
        with opener.open(request, timeout=5) as response:
            status = response.getcode()
            body = response.read(MAX_RESPONSE_BYTES + 1)
        require(200 <= status < 300, "heartbeat response status가 success가 아닙니다.")
        require(len(body) <= MAX_RESPONSE_BYTES, "heartbeat response size가 제한을 초과했습니다.")
    except urllib.error.HTTPError as error:
        error.close()
        raise DeliveryError("Uptime Kuma heartbeat delivery에 실패했습니다.") from error
    except (ContractError, OSError, ValueError, urllib.error.URLError) as error:
        raise DeliveryError("Uptime Kuma heartbeat delivery에 실패했습니다.") from error


def collect_snapshot(
    repo_root: Path,
    project_name: str,
    env_file: str,
    backup_directory: str,
) -> dict[str, Any]:
    command = [
        str(repo_root / "scripts" / "production-status.sh"),
        "--project-name",
        project_name,
        "--env-file",
        env_file,
        "--backup-dir",
        backup_directory,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise StatusUnavailableError("production status command를 실행할 수 없습니다.") from error
    if result.returncode != 0 or len(result.stdout.encode("utf-8")) > MAX_STATUS_BYTES:
        raise StatusUnavailableError("production status snapshot을 생성할 수 없습니다.")
    try:
        snapshot = json.loads(result.stdout)
        return monitor_policy.validate_snapshot(snapshot)
    except (json.JSONDecodeError, monitor_policy.ContractError, UnicodeError, TypeError, ValueError) as error:
        raise StatusUnavailableError("production status snapshot contract가 잘못됐습니다.") from error


SnapshotProvider = Callable[[Path, str, str, str], dict[str, Any]]
HeartbeatSender = Callable[[str, dict[str, Any]], None]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def run_monitor(
    *,
    repo_root: Path,
    project_name: str,
    env_file: str,
    backup_directory: str,
    state_directory_value: str,
    heartbeat_config_value: str,
    snapshot_provider: SnapshotProvider = collect_snapshot,
    heartbeat_sender: HeartbeatSender = send_heartbeat,
    now: Callable[[], dt.datetime] = _now,
) -> tuple[dict[str, Any], int]:
    state_directory = validate_state_directory(repo_root, state_directory_value)
    heartbeat_config = validate_heartbeat_config(repo_root, heartbeat_config_value)
    heartbeat_url = load_heartbeat_url(heartbeat_config)
    store = MonitorStateStore(state_directory)

    with MonitorLock(state_directory):
        try:
            snapshot = snapshot_provider(
                repo_root, project_name, env_file, backup_directory
            )
        except StatusUnavailableError:
            observed_at = now()
            require(observed_at.tzinfo is not None, "monitor clock이 timezone-aware가 아닙니다.")
            result = monitor_policy.failure_result(
                monitor_policy.format_instant(observed_at), "STATUS_UNAVAILABLE"
            )
            heartbeat_sender(heartbeat_url, result)
            return result, 1

        try:
            previous_state = store.load()
        except ContractError:
            result = monitor_policy.failure_result(
                snapshot["observedAt"], "STATE_INVALID"
            )
            heartbeat_sender(heartbeat_url, result)
            return result, 1

        try:
            result, next_state = monitor_policy.evaluate(snapshot, previous_state)
        except monitor_policy.ContractError:
            result = monitor_policy.failure_result(
                snapshot["observedAt"], "STATUS_UNAVAILABLE"
            )
            heartbeat_sender(heartbeat_url, result)
            return result, 1

        store.save(next_state)
        heartbeat_sender(heartbeat_url, result)
        return result, 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="our-ledger production status policy monitor harness"
    )
    result.add_argument("--project-name", required=True)
    result.add_argument("--env-file", required=True)
    result.add_argument("--backup-dir", required=True)
    result.add_argument("--state-dir", required=True)
    result.add_argument("--heartbeat-config", required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        result, exit_code = run_monitor(
            repo_root=repo_root,
            project_name=args.project_name,
            env_file=args.env_file,
            backup_directory=args.backup_dir,
            state_directory_value=args.state_dir,
            heartbeat_config_value=args.heartbeat_config,
        )
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        raise SystemExit(exit_code)
    except LockBusyError as error:
        print("monitor 실행이 이미 진행 중입니다.", file=sys.stderr)
        raise SystemExit(75) from error
    except DeliveryError as error:
        print("Uptime Kuma heartbeat delivery에 실패했습니다.", file=sys.stderr)
        raise SystemExit(1) from error
    except (ContractError, OSError, ValueError) as error:
        print("monitor worker contract를 실행할 수 없습니다.", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
