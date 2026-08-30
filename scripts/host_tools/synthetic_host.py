from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from scripts.host_tools.host_state import (
    ContractError,
    HostPaths,
    LockBusyError,
    OperationLock,
    ReleaseIdentity,
    begin_pending,
    commit_pending,
    initialize_layout,
    inspect_state,
    stage_release,
)
from scripts.host_tools.production_host import run_backup_core


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="test-only injected host adapter")
    parser.add_argument("--app-root", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("initialize")
    subparsers.add_parser("inspect")
    activate = subparsers.add_parser("activate")
    activate.add_argument("--source-root", required=True, type=Path)
    activate.add_argument("--application-revision", required=True)
    activate.add_argument("--runtime-config-digest", required=True)
    activate.add_argument("--runtime-config-revision", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--project-name", required=True)
    backup.add_argument("--env-file", required=True)
    backup.add_argument("--backup-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    paths = HostPaths(arguments.app_root)
    try:
        initialize_layout(paths)
        if arguments.command == "initialize":
            return 0
        with OperationLock(paths) as lock:
            state = inspect_state(paths, lock)
            if arguments.command == "inspect":
                print(json.dumps(state, separators=(",", ":"), sort_keys=True))
                return 0
            if arguments.command == "activate":
                if state["pending"]:
                    raise ContractError("host recovery is pending")
                identity = stage_release(
                    paths,
                    lock,
                    arguments.source_root,
                    application_revision=arguments.application_revision,
                    runtime_config_digest=arguments.runtime_config_digest,
                    runtime_config_revision=arguments.runtime_config_revision,
                )
                if state["status"] == "FRESH":
                    begin_pending(paths, lock, identity)
                    commit_pending(paths, lock)
                elif state["current"] != identity.to_json():
                    raise ContractError("synthetic current release differs")
                return 0
            if state["pending"]:
                raise ContractError("host recovery is pending")
            if state["status"] != "READY":
                raise ContractError("synthetic runtime release is not active")
            current = ReleaseIdentity.from_json(state["current"])
            core_path = (
                paths.releases
                / current.release_name
                / "scripts"
                / "backup_tools"
                / "backup_core.sh"
            )
            return run_backup_core(
                [
                    "--project-name",
                    arguments.project_name,
                    "--env-file",
                    str(arguments.env_file),
                    "--backup-dir",
                    str(arguments.backup_dir),
                ],
                paths=paths,
                lock=lock,
                core_path=core_path,
            )
    except (ContractError, LockBusyError, OSError):
        print("synthetic host operation contract failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
