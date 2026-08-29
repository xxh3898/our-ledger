from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from scripts.host_tools.host_state import (
    ContractError,
    HostPaths,
    LockBusyError,
    OperationLock,
    inspect_state,
    production_paths,
    validate_layout,
)


BACKUP_CORE = Path(__file__).resolve().parents[1] / "backup_tools" / "backup_core.sh"
Runner = Callable[[Sequence[str]], int]


def _run_process(arguments: Sequence[str]) -> int:
    return subprocess.run(arguments, check=False, shell=False).returncode


def run_backup_core(
    arguments: Sequence[str],
    *,
    paths: HostPaths,
    lock: OperationLock,
    core_path: Path = BACKUP_CORE,
    runner: Runner = _run_process,
) -> int:
    lock.assert_held(paths)
    core_stat = os.lstat(core_path)
    if not stat.S_ISREG(core_stat.st_mode) or core_stat.st_nlink != 1:
        raise ContractError("internal backup core authority is invalid")
    return runner(["/bin/bash", str(core_path), *arguments])


def run_standalone_backup(
    arguments: Sequence[str],
    *,
    paths=None,
    runner: Runner = _run_process,
) -> int:
    injected_paths = paths is not None
    selected_paths = paths if injected_paths else production_paths()
    validate_layout(selected_paths)
    if not injected_paths:
        _validate_production_worker_source(selected_paths)
    with OperationLock(selected_paths) as lock:
        state = inspect_state(selected_paths, lock)
        if state["pending"]:
            raise ContractError("host recovery is pending")
        return run_backup_core(
            arguments,
            paths=selected_paths,
            lock=lock,
            runner=runner,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup-production.sh",
        description="our-ledger fixed host operation worker",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup", help="shared-lock standalone backup")
    backup.add_argument("--project-name", required=True)
    backup.add_argument("--env-file", required=True)
    backup.add_argument("--backup-dir", required=True)
    subparsers.add_parser("inspect", help="inspect fixed host state")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "backup":
            return run_standalone_backup(
                [
                    "--project-name",
                    arguments.project_name,
                    "--env-file",
                    arguments.env_file,
                    "--backup-dir",
                    arguments.backup_dir,
                ]
            )
        paths = production_paths()
        validate_layout(paths)
        _validate_production_worker_source(paths)
        with OperationLock(paths) as lock:
            result = inspect_state(paths, lock)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0
    except (ContractError, LockBusyError, OSError):
        print("host operation contract failed", file=sys.stderr)
        return 1


def _validate_production_worker_source(paths) -> None:
    expected = paths.current / "scripts" / "host_tools" / "production_host.py"
    try:
        actual_path = Path(__file__).resolve(strict=True)
        expected_path = expected.resolve(strict=True)
        actual_stat = os.lstat(actual_path)
        expected_stat = os.lstat(expected_path)
    except OSError as error:
        raise ContractError("production host worker source is unavailable") from error
    if actual_path != expected_path or (
        actual_stat.st_dev,
        actual_stat.st_ino,
    ) != (expected_stat.st_dev, expected_stat.st_ino):
        raise ContractError("production host worker is not the verified current release")
    if not stat.S_ISREG(actual_stat.st_mode) or actual_stat.st_nlink != 1:
        raise ContractError("production host worker source is invalid")


if __name__ == "__main__":
    raise SystemExit(main())
