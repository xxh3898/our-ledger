#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path, PurePath
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable

from scripts.backup_tools import backup_artifact
from scripts.status_tools import monitor_policy


STATE_FILENAME = "monitor-state.json"
LOCK_FILENAME = ".our-ledger-monitor.lock"
MAX_PRIVATE_FILE_BYTES = 65_536
MAX_STATUS_BYTES = 1_048_576
MAX_HOMEOPS_PAYLOAD_BYTES = 4_096
HOMEOPS_REPORTER_FILENAME = "report-homeops-event.py"
HOMEOPS_REPORTER_TIMEOUT_SECONDS = 5


class ContractError(RuntimeError):
    pass


class LockBusyError(ContractError):
    pass


class StatusUnavailableError(ContractError):
    pass


class ReporterError(ContractError):
    pass


@dataclass(frozen=True)
class HomeOpsReporter:
    path: Path
    device: int
    inode: int


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


def validate_backup_directory(repo_root: Path, value: str) -> Path:
    try:
        return backup_artifact.validate_backup_directory_read_only(
            str(repo_root), value
        )
    except backup_artifact.ContractError as error:
        raise ContractError("backup directory contract가 잘못됐습니다.") from error


def validate_disjoint_paths(*authorities: Path) -> None:
    for index, candidate in enumerate(authorities):
        for other in authorities[index + 1:]:
            require(
                not _is_within(candidate, other)
                and not _is_within(other, candidate),
                "monitor authority path는 서로 disjoint여야 합니다.",
            )


def validate_state_directory_entries(state_directory: Path) -> None:
    allowed = {STATE_FILENAME, LOCK_FILENAME}
    try:
        entries = list(state_directory.iterdir())
    except OSError as error:
        raise ContractError("monitor state directory entry를 확인할 수 없습니다.") from error
    require(
        all(entry.name in allowed for entry in entries),
        "monitor state directory에 예상 밖 entry가 있습니다.",
    )


def _reporter_info(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as error:
        raise ContractError(f"{label} metadata를 확인할 수 없습니다.") from error
    require(not stat.S_ISLNK(info.st_mode), f"{label}는 symlink일 수 없습니다.")
    require(stat.S_ISREG(info.st_mode), f"{label}는 regular file이어야 합니다.")
    require(info.st_uid == os.geteuid(), f"{label} owner가 현재 실행 사용자와 다릅니다.")
    mode = stat.S_IMODE(info.st_mode)
    require(mode & 0o022 == 0, f"{label}는 group/other writable일 수 없습니다.")
    require(mode & stat.S_IXUSR != 0, f"{label}에 owner executable bit가 필요합니다.")
    return info


def validate_homeops_reporter(repo_root: Path, value: str) -> HomeOpsReporter:
    candidate = _raw_path(value, "HomeOps reporter")
    require(
        candidate.name == HOMEOPS_REPORTER_FILENAME,
        "HomeOps reporter identity가 잘못됐습니다.",
    )
    before = _reporter_info(candidate, "HomeOps reporter")
    try:
        canonical = candidate.resolve(strict=True)
        canonical_repo = repo_root.resolve(strict=True)
    except OSError as error:
        raise ContractError("HomeOps reporter path를 canonicalize할 수 없습니다.") from error
    require(
        canonical.name == HOMEOPS_REPORTER_FILENAME,
        "HomeOps reporter canonical identity가 잘못됐습니다.",
    )
    require(
        not _is_within(canonical, canonical_repo),
        "HomeOps reporter는 repository 밖에 있어야 합니다.",
    )
    after = _reporter_info(canonical, "HomeOps reporter")
    require(
        (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
        "HomeOps reporter가 resolve 중 교체됐습니다.",
    )
    return HomeOpsReporter(canonical, after.st_dev, after.st_ino)


def _revalidate_homeops_reporter(reporter: HomeOpsReporter) -> None:
    info = _reporter_info(reporter.path, "HomeOps reporter")
    require(
        (info.st_dev, info.st_ino) == (reporter.device, reporter.inode),
        "HomeOps reporter가 validation 이후 교체됐습니다.",
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


def _homeops_payload_bytes(payload: dict[str, Any]) -> bytes:
    try:
        validated = monitor_policy.validate_homeops_disk_signal(payload)
    except monitor_policy.ContractError as error:
        raise ContractError("HomeOps signal payload contract가 잘못됐습니다.") from error
    content = (
        json.dumps(validated, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    require(
        len(content) <= MAX_HOMEOPS_PAYLOAD_BYTES,
        "HomeOps signal payload size가 제한을 초과했습니다.",
    )
    return content


def send_homeops_signal(reporter: HomeOpsReporter, payload: dict[str, Any]) -> None:
    content = _homeops_payload_bytes(payload)
    try:
        _revalidate_homeops_reporter(reporter)
        result = subprocess.run(
            [str(reporter.path), "signal"],
            input=content,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=HOMEOPS_REPORTER_TIMEOUT_SECONDS,
        )
    except (ContractError, OSError, subprocess.SubprocessError) as error:
        raise ReporterError("HomeOps reporter가 signal을 수락하지 못했습니다.") from error
    if result.returncode != 0:
        raise ReporterError("HomeOps reporter가 signal을 수락하지 못했습니다.")


def _homeops_signal(
    *, episode_key: str, status: str, observed_at: str, used_percent: int | float
) -> dict[str, Any]:
    available_percent = round(100.0 - float(used_percent), 2)
    payload = {
        "eventKey": f"{episode_key}:{'alert' if status == 'ALERT' else 'recovered'}",
        "episodeKey": episode_key,
        "project": monitor_policy.HOMEOPS_PROJECT,
        "signalType": "DISK_LOW",
        "status": status,
        "observedAt": observed_at,
        "availablePercent": available_percent,
        "thresholdPercent": monitor_policy.HOMEOPS_DISK_THRESHOLD_PERCENT,
    }
    return monitor_policy.validate_homeops_disk_signal(payload)


def prepare_homeops_disk_transition(
    snapshot: dict[str, Any], state: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    validated_snapshot = monitor_policy.validate_snapshot(snapshot)
    next_state = monitor_policy.validate_state(state)
    disk_state = next_state["homeOpsDisk"]
    require(
        disk_state["pendingSignal"] is None,
        "새 HomeOps transition 전에 pending signal이 없어야 합니다.",
    )
    filesystem = validated_snapshot["filesystem"]
    if filesystem["state"] != "AVAILABLE":
        return next_state, None

    used_percent = filesystem["usedPercent"]
    active_episode = disk_state["activeEpisodeKey"]
    payload: dict[str, Any] | None = None
    if used_percent >= 80 and active_episode is None:
        sequence = disk_state["episodeSequence"]
        require(
            sequence < monitor_policy.MAX_EPISODE_SEQUENCE,
            "HomeOps disk episode sequence가 제한을 초과했습니다.",
        )
        sequence += 1
        episode_key = f"{monitor_policy.HOMEOPS_PROJECT}:disk-low:{sequence}"
        disk_state["episodeSequence"] = sequence
        payload = _homeops_signal(
            episode_key=episode_key,
            status="ALERT",
            observed_at=validated_snapshot["observedAt"],
            used_percent=used_percent,
        )
    elif used_percent < 80 and active_episode is not None:
        payload = _homeops_signal(
            episode_key=active_episode,
            status="RECOVERED",
            observed_at=validated_snapshot["observedAt"],
            used_percent=used_percent,
        )
    disk_state["pendingSignal"] = payload
    return monitor_policy.validate_state(next_state), payload


def finalize_homeops_pending(state: dict[str, Any]) -> dict[str, Any]:
    next_state = monitor_policy.validate_state(state)
    disk_state = next_state["homeOpsDisk"]
    pending = disk_state["pendingSignal"]
    require(pending is not None, "finalize할 HomeOps pending signal이 없습니다.")
    if pending["status"] == "ALERT":
        disk_state["activeEpisodeKey"] = pending["episodeKey"]
    else:
        disk_state["activeEpisodeKey"] = None
    disk_state["pendingSignal"] = None
    return monitor_policy.validate_state(next_state)


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
HomeOpsSender = Callable[[HomeOpsReporter, dict[str, Any]], None]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def run_monitor(
    *,
    repo_root: Path,
    project_name: str,
    env_file: str,
    backup_directory: str,
    state_directory_value: str,
    homeops_reporter_value: str,
    snapshot_provider: SnapshotProvider = collect_snapshot,
    homeops_sender: HomeOpsSender = send_homeops_signal,
    now: Callable[[], dt.datetime] = _now,
) -> tuple[dict[str, Any], int]:
    backup_directory_path = validate_backup_directory(repo_root, backup_directory)
    state_directory = validate_state_directory(repo_root, state_directory_value)
    homeops_reporter = validate_homeops_reporter(repo_root, homeops_reporter_value)
    validate_disjoint_paths(
        state_directory, backup_directory_path, homeops_reporter.path
    )
    validate_state_directory_entries(state_directory)
    store = MonitorStateStore(state_directory)

    with MonitorLock(state_directory):
        try:
            previous_state = store.load()
        except ContractError:
            observed_at = now()
            require(observed_at.tzinfo is not None, "monitor clock이 timezone-aware가 아닙니다.")
            return monitor_policy.failure_result(
                monitor_policy.format_instant(observed_at), "STATE_INVALID"
            ), 1

        pending = previous_state["homeOpsDisk"]["pendingSignal"]
        if pending is not None:
            homeops_sender(homeops_reporter, pending)
            previous_state = finalize_homeops_pending(previous_state)
            store.save(previous_state)

        try:
            snapshot = snapshot_provider(
                repo_root, project_name, env_file, str(backup_directory_path)
            )
        except StatusUnavailableError:
            observed_at = now()
            require(observed_at.tzinfo is not None, "monitor clock이 timezone-aware가 아닙니다.")
            result = monitor_policy.failure_result(
                monitor_policy.format_instant(observed_at), "STATUS_UNAVAILABLE"
            )
            return result, 1

        try:
            result, next_state = monitor_policy.evaluate(snapshot, previous_state)
        except monitor_policy.ContractError:
            result = monitor_policy.failure_result(
                snapshot["observedAt"], "STATUS_UNAVAILABLE"
            )
            return result, 1

        next_state, pending = prepare_homeops_disk_transition(snapshot, next_state)
        store.save(next_state)
        if pending is not None:
            homeops_sender(homeops_reporter, pending)
            store.save(finalize_homeops_pending(next_state))
        return result, 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="our-ledger production status policy monitor harness"
    )
    result.add_argument("--project-name", required=True)
    result.add_argument("--env-file", required=True)
    result.add_argument("--backup-dir", required=True)
    result.add_argument("--state-dir", required=True)
    result.add_argument("--homeops-reporter", required=True)
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
            homeops_reporter_value=args.homeops_reporter,
        )
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        raise SystemExit(exit_code)
    except LockBusyError as error:
        print("monitor 실행이 이미 진행 중입니다.", file=sys.stderr)
        raise SystemExit(75) from error
    except ReporterError as error:
        print("HomeOps reporter가 signal을 수락하지 못했습니다.", file=sys.stderr)
        raise SystemExit(1) from error
    except (ContractError, OSError, ValueError) as error:
        print("monitor worker contract를 실행할 수 없습니다.", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
