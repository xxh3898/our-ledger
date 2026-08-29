#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePath
import re
import secrets
import stat
import sys
import tempfile
from typing import Any


FORMAT_VERSION = 1
PRODUCT_PREFIX = "our-ledger_production"
STEM_PATTERN = re.compile(
    rf"^(?P<prefix>{PRODUCT_PREFIX})_"
    r"(?P<timestamp>[0-9]{8}T[0-9]{6}Z)_"
    r"v(?P<schema>[1-9][0-9]*(?:[.][0-9]+)*)_"
    r"(?P<suffix>[0-9a-f]{12})$"
)
SCHEMA_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*(?:[.][0-9]+)*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PROJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
PG_DUMP_VERSION_PATTERN = re.compile(r"^pg_dump [(]PostgreSQL[)] 18[.]6(?:\s|$)")
SERVER_VERSION_PATTERN = re.compile(r"^18[.]6(?:\s|$)")
METADATA_KEYS = {
    "formatVersion",
    "createdAt",
    "schemaVersion",
    "sizeBytes",
    "sha256",
    "dumpFilename",
    "pgDumpVersion",
    "postgresServerVersion",
}
MARKER_KEYS = METADATA_KEYS | {"bundleDirectory"}


class ContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _raw_path(value: str, label: str) -> Path:
    require(bool(value), f"{label} path가 비어 있습니다.")
    require(not _has_control(value), f"{label} path에 control 문자를 사용할 수 없습니다.")
    candidate = Path(value)
    require(candidate.is_absolute(), f"{label} path는 absolute path여야 합니다.")
    require(".." not in PurePath(value).parts, f"{label} path에 '..'를 사용할 수 없습니다.")
    return candidate


def _canonical_existing(value: str, label: str) -> Path:
    candidate = _raw_path(value, label)
    require(candidate.exists(), f"{label} path가 존재하지 않습니다.")
    require(not candidate.is_symlink(), f"{label} path는 symlink일 수 없습니다.")
    try:
        return candidate.resolve(strict=True)
    except OSError as error:
        raise ContractError(f"{label} path를 canonicalize할 수 없습니다.") from error


def _is_within(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


def _require_owner_only_info(
    info: os.stat_result, label: str, *, directory: bool
) -> os.stat_result:
    if directory:
        require(stat.S_ISDIR(info.st_mode), f"{label}는 directory여야 합니다.")
        require(info.st_mode & stat.S_IWUSR, f"{label}에 owner write 권한이 필요합니다.")
        require(info.st_mode & stat.S_IXUSR, f"{label}에 owner execute 권한이 필요합니다.")
    else:
        require(stat.S_ISREG(info.st_mode), f"{label}는 regular file이어야 합니다.")
        require(info.st_mode & stat.S_IRUSR, f"{label}에 owner read 권한이 필요합니다.")
    require(info.st_uid == os.geteuid(), f"{label}의 owner가 현재 실행 사용자와 다릅니다.")
    require(
        stat.S_IMODE(info.st_mode) & 0o077 == 0,
        f"{label}는 group/other 권한이 없어야 합니다.",
    )
    return info


def _require_owner_only(item: Path, label: str, *, directory: bool) -> os.stat_result:
    return _require_owner_only_info(item.stat(), label, directory=directory)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_env_path(repo_root_value: str, env_path_value: str) -> Path:
    repo_root = _canonical_existing(repo_root_value, "repository root")
    env_path = _canonical_existing(env_path_value, "env file")
    require(not _is_within(env_path, repo_root), "env file은 repository 밖에 있어야 합니다.")
    _require_owner_only(env_path, "env file", directory=False)
    return env_path


def _dangerous_backup_roots(repo_root: Path) -> list[Path]:
    home = Path.home().resolve()
    candidates = [
        Path("/"),
        home,
        repo_root,
        repo_root.parent,
        home / "Server",
        home / "Server" / "data",
        home / "Server" / "backups",
    ]
    return [candidate.resolve() for candidate in candidates if candidate.exists()]


def _docker_data_roots() -> list[Path]:
    candidates = [
        Path("/var/lib/docker"),
        Path("/var/lib/containers"),
        Path("/var/lib/postgresql"),
        Path.home() / "Library" / "Containers" / "com.docker.docker",
    ]
    return [candidate.resolve() for candidate in candidates if candidate.exists()]


def validate_backup_directory_read_only(
    repo_root_value: str, backup_path_value: str
) -> Path:
    repo_root = _canonical_existing(repo_root_value, "repository root")
    backup_path = _canonical_existing(backup_path_value, "backup directory")
    _require_owner_only(backup_path, "backup directory", directory=True)

    for dangerous_root in _dangerous_backup_roots(repo_root):
        require(
            backup_path != dangerous_root,
            "backup directory가 broad 또는 protected root와 같습니다.",
        )
    require(
        not _is_within(backup_path, repo_root),
        "backup directory는 repository 밖에 있어야 합니다.",
    )
    for docker_root in _docker_data_roots():
        require(
            not _is_within(backup_path, docker_root),
            "backup directory로 Docker/PostgreSQL data path를 사용할 수 없습니다.",
        )
    return backup_path


def validate_backup_directory(repo_root_value: str, backup_path_value: str) -> Path:
    backup_path = validate_backup_directory_read_only(
        repo_root_value, backup_path_value
    )

    descriptor, probe_name = tempfile.mkstemp(
        prefix=".our-ledger-write-probe.", dir=backup_path
    )
    probe_path = Path(probe_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
        probe_path.unlink(missing_ok=True)
    _fsync_directory(backup_path)
    return backup_path


def parse_created_at(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ContractError("createdAt은 초 단위 UTC timestamp여야 합니다.") from error
    return parsed.replace(tzinfo=dt.timezone.utc)


def validate_schema_version(value: str) -> str:
    require(bool(SCHEMA_VERSION_PATTERN.fullmatch(value)), "Flyway schema version 형식이 잘못됐습니다.")
    return value


def create_stem(created_at: str, schema_version: str) -> str:
    timestamp = parse_created_at(created_at).strftime("%Y%m%dT%H%M%SZ")
    schema_version = validate_schema_version(schema_version)
    return f"{PRODUCT_PREFIX}_{timestamp}_v{schema_version}_{secrets.token_hex(6)}"


def parse_stem(stem: str) -> re.Match[str]:
    matched = STEM_PATTERN.fullmatch(stem)
    require(matched is not None, "backup artifact 이름이 strict contract와 다릅니다.")
    return matched


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_exclusive(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_direct_child(child: Path, parent: Path, label: str) -> None:
    require(child.parent == parent, f"{label}는 backup directory의 direct child여야 합니다.")


def _validate_staging_directory(backup_directory: Path, staging_directory: Path) -> None:
    _require_direct_child(staging_directory, backup_directory, "staging directory")
    require(
        staging_directory.name.startswith(".our-ledger_backup_")
        and staging_directory.name.endswith(".partial"),
        "staging directory 이름이 안전한 partial contract와 다릅니다.",
    )
    require(staging_directory.exists(), "staging directory가 존재하지 않습니다.")
    require(not staging_directory.is_symlink(), "staging directory는 symlink일 수 없습니다.")
    _require_owner_only(staging_directory, "staging directory", directory=True)


def _dump_stem_for_staging(staging_directory: Path, dump_filename: str) -> str:
    require(bool(dump_filename), "dump filename이 비어 있습니다.")
    require(not _has_control(dump_filename), "dump filename에 control 문자를 사용할 수 없습니다.")
    require(
        PurePath(dump_filename).parts == (dump_filename,),
        "dump는 staging directory의 direct child여야 합니다.",
    )
    require(dump_filename.endswith(".dump"), "dump filename 확장자가 잘못됐습니다.")
    stem = dump_filename.removesuffix(".dump")
    parse_stem(stem)
    require(
        staging_directory.name == f".our-ledger_backup_{stem}.partial",
        "staging directory와 expected dump filename이 다릅니다.",
    )
    return stem


def fsync_dump_file(
    backup_directory: Path,
    staging_directory: Path,
    dump_filename: str,
) -> os.stat_result:
    _validate_staging_directory(backup_directory, staging_directory)
    _dump_stem_for_staging(staging_directory, dump_filename)

    directory_descriptor = -1
    dump_descriptor = -1
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(staging_directory, directory_flags)
        directory_info = os.fstat(directory_descriptor)
        _require_owner_only_info(
            directory_info, "staging directory", directory=True
        )

        before_open = os.stat(
            dump_filename,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        _require_owner_only_info(before_open, "partial dump", directory=False)

        dump_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        dump_flags |= getattr(os, "O_NOFOLLOW", 0)
        dump_descriptor = os.open(
            dump_filename,
            dump_flags,
            dir_fd=directory_descriptor,
        )
        after_open = os.fstat(dump_descriptor)
        _require_owner_only_info(after_open, "partial dump", directory=False)
        require(
            (before_open.st_dev, before_open.st_ino)
            == (after_open.st_dev, after_open.st_ino),
            "partial dump가 fsync open 중 교체됐습니다.",
        )
        require(after_open.st_size > 0, "partial dump가 비어 있습니다.")
        os.fsync(dump_descriptor)
        return after_open
    except ContractError:
        raise
    except OSError as error:
        raise ContractError("partial dump file을 fsync할 수 없습니다.") from error
    finally:
        if dump_descriptor >= 0:
            os.close(dump_descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def write_sidecars(
    backup_directory: Path,
    staging_directory: Path,
    dump_filename: str,
    created_at: str,
    schema_version: str,
    pg_dump_version: str,
    postgres_server_version: str,
) -> dict[str, Any]:
    _validate_staging_directory(backup_directory, staging_directory)
    stem = _dump_stem_for_staging(staging_directory, dump_filename)
    matched = parse_stem(stem)
    parsed_created_at = parse_created_at(created_at)
    schema_version = validate_schema_version(schema_version)
    require(
        matched.group("timestamp") == parsed_created_at.strftime("%Y%m%dT%H%M%SZ"),
        "dump filename timestamp와 metadata timestamp가 다릅니다.",
    )
    require(matched.group("schema") == schema_version, "dump filename schema version이 다릅니다.")
    require(bool(PG_DUMP_VERSION_PATTERN.match(pg_dump_version)), "pg_dump 18.6 client가 아닙니다.")
    require(
        bool(SERVER_VERSION_PATTERN.match(postgres_server_version)),
        "PostgreSQL 18.6 server가 아닙니다.",
    )

    dump_path = staging_directory / dump_filename
    require(dump_path.exists() and not dump_path.is_symlink(), "partial dump가 없습니다.")
    dump_info = _require_owner_only(dump_path, "partial dump", directory=False)
    require(dump_info.st_size > 0, "partial dump가 비어 있습니다.")
    with dump_path.open("rb") as source:
        require(source.read(5) == b"PGDMP", "PostgreSQL custom archive magic이 없습니다.")

    sha256 = _hash_file(dump_path)
    metadata = {
        "formatVersion": FORMAT_VERSION,
        "createdAt": created_at,
        "schemaVersion": schema_version,
        "sizeBytes": dump_info.st_size,
        "sha256": sha256,
        "dumpFilename": dump_filename,
        "pgDumpVersion": pg_dump_version,
        "postgresServerVersion": postgres_server_version,
    }
    metadata_path = staging_directory / f"{stem}.json"
    checksum_path = staging_directory / f"{stem}.sha256"
    _write_exclusive(
        metadata_path,
        (json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(),
    )
    _write_exclusive(checksum_path, f"{sha256}  {dump_filename}\n".encode())
    _fsync_directory(staging_directory)
    return metadata


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"{label} JSON을 읽을 수 없습니다.") from error
    require(isinstance(value, dict), f"{label} JSON은 object여야 합니다.")
    return value


def _validate_metadata(metadata: dict[str, Any], stem: str) -> None:
    require(set(metadata) == METADATA_KEYS, "backup metadata field가 exact contract와 다릅니다.")
    require(metadata["formatVersion"] == FORMAT_VERSION, "metadata formatVersion이 다릅니다.")
    require(type(metadata["sizeBytes"]) is int and metadata["sizeBytes"] > 0, "metadata sizeBytes가 잘못됐습니다.")
    require(type(metadata["schemaVersion"]) is str, "metadata schemaVersion type이 잘못됐습니다.")
    validate_schema_version(metadata["schemaVersion"])
    require(type(metadata["createdAt"]) is str, "metadata createdAt type이 잘못됐습니다.")
    created_at = parse_created_at(metadata["createdAt"])
    require(type(metadata["sha256"]) is str and bool(SHA256_PATTERN.fullmatch(metadata["sha256"])), "metadata SHA-256이 잘못됐습니다.")
    require(metadata["dumpFilename"] == f"{stem}.dump", "metadata dumpFilename이 다릅니다.")
    require(type(metadata["pgDumpVersion"]) is str and bool(PG_DUMP_VERSION_PATTERN.match(metadata["pgDumpVersion"])), "metadata pg_dump version이 다릅니다.")
    require(type(metadata["postgresServerVersion"]) is str and bool(SERVER_VERSION_PATTERN.match(metadata["postgresServerVersion"])), "metadata server version이 다릅니다.")

    matched = parse_stem(stem)
    require(
        matched.group("timestamp") == created_at.strftime("%Y%m%dT%H%M%SZ"),
        "metadata와 artifact timestamp가 다릅니다.",
    )
    require(matched.group("schema") == metadata["schemaVersion"], "metadata와 artifact schema version이 다릅니다.")


def verify_bundle(bundle_directory: Path, *, allow_staging: bool = False) -> dict[str, Any]:
    require(bundle_directory.exists(), "backup bundle이 존재하지 않습니다.")
    require(not bundle_directory.is_symlink(), "backup bundle은 symlink일 수 없습니다.")
    _require_owner_only(bundle_directory, "backup bundle", directory=True)

    entries = list(bundle_directory.iterdir())
    require(all(not item.is_symlink() for item in entries), "backup bundle 안에 symlink가 있습니다.")
    dump_files = [item for item in entries if item.name.endswith(".dump")]
    require(len(dump_files) == 1, "backup bundle에는 dump가 정확히 하나 있어야 합니다.")
    stem = dump_files[0].name.removesuffix(".dump")
    parse_stem(stem)
    expected_names = {f"{stem}.dump", f"{stem}.json", f"{stem}.sha256"}
    require({item.name for item in entries} == expected_names, "backup bundle file set이 exact contract와 다릅니다.")

    if not allow_staging:
        require(bundle_directory.name == f"{stem}.backup", "final bundle directory 이름이 dump stem과 다릅니다.")

    dump_path = bundle_directory / f"{stem}.dump"
    metadata_path = bundle_directory / f"{stem}.json"
    checksum_path = bundle_directory / f"{stem}.sha256"
    for item, label in (
        (dump_path, "dump"),
        (metadata_path, "metadata"),
        (checksum_path, "checksum"),
    ):
        _require_owner_only(item, label, directory=False)

    metadata = _load_json_object(metadata_path, "backup metadata")
    _validate_metadata(metadata, stem)
    size = dump_path.stat().st_size
    require(size == metadata["sizeBytes"], "dump size와 metadata가 다릅니다.")
    require(size > 0, "dump가 비어 있습니다.")
    with dump_path.open("rb") as source:
        require(source.read(5) == b"PGDMP", "PostgreSQL custom archive magic이 없습니다.")
    sha256 = _hash_file(dump_path)
    require(sha256 == metadata["sha256"], "dump SHA-256과 metadata가 다릅니다.")
    try:
        checksum = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise ContractError("checksum file을 읽을 수 없습니다.") from error
    require(checksum == f"{sha256}  {dump_path.name}\n", "checksum file 내용이 다릅니다.")
    return metadata


def _validate_marker(marker: dict[str, Any]) -> None:
    require(set(marker) == MARKER_KEYS, "last-success marker field가 exact contract와 다릅니다.")
    bundle_name = marker.get("bundleDirectory")
    require(type(bundle_name) is str and bundle_name.endswith(".backup"), "marker bundleDirectory가 잘못됐습니다.")
    stem = bundle_name.removesuffix(".backup")
    _validate_metadata({key: marker[key] for key in METADATA_KEYS}, stem)


def _marker_content(metadata: dict[str, Any], bundle_name: str) -> bytes:
    marker = dict(metadata)
    marker["bundleDirectory"] = bundle_name
    return (json.dumps(marker, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def _write_temp_file(directory: Path, prefix: str, content: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=prefix, dir=directory)
    path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _remove_bundle_tree(path: Path) -> None:
    require(path.exists() and not path.is_symlink(), "cleanup bundle 경계가 잘못됐습니다.")
    for child in path.iterdir():
        require(child.is_file() and not child.is_symlink(), "cleanup bundle에 예상 밖 entry가 있습니다.")
        child.unlink()
    path.rmdir()


def commit_bundle(
    backup_directory: Path,
    staging_directory: Path,
    final_bundle_name: str,
) -> Path:
    _validate_staging_directory(backup_directory, staging_directory)
    require(final_bundle_name.endswith(".backup"), "final bundle 확장자가 잘못됐습니다.")
    stem = final_bundle_name.removesuffix(".backup")
    parse_stem(stem)
    final_directory = backup_directory / final_bundle_name
    _require_direct_child(final_directory, backup_directory, "final bundle")
    require(not os.path.lexists(final_directory), "같은 final backup artifact가 이미 존재합니다.")

    metadata = verify_bundle(staging_directory, allow_staging=True)
    require(metadata["dumpFilename"] == f"{stem}.dump", "staging dump와 final bundle 이름이 다릅니다.")

    marker_path = backup_directory / "last-success.json"
    previous_marker: bytes | None = None
    if os.path.lexists(marker_path):
        require(marker_path.is_file() and not marker_path.is_symlink(), "기존 last-success marker가 regular file이 아닙니다.")
        _require_owner_only(marker_path, "last-success marker", directory=False)
        previous_marker_object = _load_json_object(marker_path, "last-success marker")
        _validate_marker(previous_marker_object)
        previous_marker = marker_path.read_bytes()

    marker_temp = _write_temp_file(
        backup_directory,
        ".last-success.",
        _marker_content(metadata, final_bundle_name),
    )
    final_created = False
    marker_replaced = False
    try:
        require(not os.path.lexists(final_directory), "final bundle collision이 발생했습니다.")
        os.rename(staging_directory, final_directory)
        final_created = True
        _fsync_directory(backup_directory)
        os.replace(marker_temp, marker_path)
        marker_replaced = True
        _fsync_directory(backup_directory)
    except BaseException:
        if marker_temp.exists():
            marker_temp.unlink()
        if marker_replaced:
            if previous_marker is None:
                marker_path.unlink(missing_ok=True)
            else:
                rollback_temp = _write_temp_file(
                    backup_directory,
                    ".last-success.rollback.",
                    previous_marker,
                )
                os.replace(rollback_temp, marker_path)
        if final_created and final_directory.exists():
            _remove_bundle_tree(final_directory)
        _fsync_directory(backup_directory)
        raise

    return final_directory / metadata["dumpFilename"]


def cleanup_staging(backup_directory: Path, staging_directory: Path) -> None:
    if not staging_directory.exists():
        return
    _validate_staging_directory(backup_directory, staging_directory)
    for child in staging_directory.iterdir():
        require(child.is_file() and not child.is_symlink(), "partial cleanup 대상에 예상 밖 entry가 있습니다.")
        child.unlink()
    staging_directory.rmdir()
    _fsync_directory(backup_directory)


def inventory(backup_directory: Path) -> dict[str, Any]:
    marker_bundle: str | None = None
    marker_path = backup_directory / "last-success.json"
    if marker_path.exists() and marker_path.is_file() and not marker_path.is_symlink():
        try:
            marker = _load_json_object(marker_path, "last-success marker")
            _validate_marker(marker)
            marker_bundle = marker["bundleDirectory"]
        except ContractError:
            marker_bundle = None

    valid: list[dict[str, Any]] = []
    invalid: list[str] = []
    incomplete: list[str] = []
    foreign: list[str] = []
    for item in sorted(backup_directory.iterdir(), key=lambda candidate: candidate.name):
        if item.name in {"last-success.json", ".our-ledger-backup.lock"}:
            continue
        if item.name.endswith(".partial"):
            incomplete.append(item.name)
            continue
        if item.is_dir() and item.name.endswith(".backup"):
            try:
                metadata = verify_bundle(item)
                valid.append(
                    {
                        "bundleDirectory": item.name,
                        "createdAt": metadata["createdAt"],
                        "schemaVersion": metadata["schemaVersion"],
                        "sizeBytes": metadata["sizeBytes"],
                        "isLatest": item.name == marker_bundle,
                    }
                )
            except ContractError:
                invalid.append(item.name)
            continue
        foreign.append(item.name)
    return {
        "formatVersion": FORMAT_VERSION,
        "valid": valid,
        "invalid": invalid,
        "incomplete": incomplete,
        "foreign": foreign,
        "lastSuccessValid": marker_bundle is not None
        and any(item["bundleDirectory"] == marker_bundle for item in valid),
    }


def check_postgres_container(
    payload: Any,
    project_name: str,
    compose_file: Path,
    expected_image: str,
) -> None:
    require(bool(PROJECT_PATTERN.fullmatch(project_name)), "Compose project 이름이 안전한 형식이 아닙니다.")
    require(isinstance(payload, list) and len(payload) == 1, "postgres container는 정확히 하나여야 합니다.")
    container = payload[0]
    labels = container.get("Config", {}).get("Labels", {}) or {}
    require(labels.get("com.docker.compose.project") == project_name, "postgres container project label이 다릅니다.")
    require(labels.get("com.docker.compose.service") == "postgres", "postgres service label이 다릅니다.")
    config_files = labels.get("com.docker.compose.project.config_files", "")
    resolved_config_files = {
        Path(value).resolve() for value in config_files.split(",") if value
    }
    require(resolved_config_files == {compose_file.resolve()}, "postgres container의 Compose file authority가 다릅니다.")
    require(container.get("Config", {}).get("Image") == expected_image, "postgres image가 pinned 18.6 contract와 다릅니다.")

    state = container.get("State", {}) or {}
    require(state.get("Status") == "running", "postgres container가 running 상태가 아닙니다.")
    require((state.get("Health") or {}).get("Status") == "healthy", "postgres container가 healthy 상태가 아닙니다.")
    host = container.get("HostConfig", {}) or {}
    require(not (host.get("PortBindings") or {}), "postgres container가 host port를 publish합니다.")
    require(host.get("NetworkMode") != "host", "postgres container가 host network를 사용합니다.")

    mounts = container.get("Mounts", []) or []
    require(len(mounts) == 1, "postgres data mount가 정확히 하나가 아닙니다.")
    mount = mounts[0]
    require(mount.get("Type") == "volume", "postgres data mount가 named volume이 아닙니다.")
    require(mount.get("Destination") == "/var/lib/postgresql", "postgres data volume target이 다릅니다.")
    require(str(mount.get("Name", "")).startswith(f"{project_name}_"), "postgres volume이 Compose project에 격리되지 않았습니다.")

    networks = set((container.get("NetworkSettings", {}).get("Networks", {}) or {}).keys())
    require(networks == {f"{project_name}_database"}, "postgres network가 project database network에 격리되지 않았습니다.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="our-ledger backup artifact contract helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_env = subparsers.add_parser("validate-env")
    validate_env.add_argument("--repo-root", required=True)
    validate_env.add_argument("--path", required=True)

    validate_backup = subparsers.add_parser("validate-backup-dir")
    validate_backup.add_argument("--repo-root", required=True)
    validate_backup.add_argument("--path", required=True)

    new_stem = subparsers.add_parser("new-stem")
    new_stem.add_argument("--created-at", required=True)
    new_stem.add_argument("--schema-version", required=True)

    fsync_dump = subparsers.add_parser("fsync-dump")
    fsync_dump.add_argument("--backup-dir", required=True)
    fsync_dump.add_argument("--staging-dir", required=True)
    fsync_dump.add_argument("--dump-filename", required=True)

    write = subparsers.add_parser("write-sidecars")
    write.add_argument("--backup-dir", required=True)
    write.add_argument("--staging-dir", required=True)
    write.add_argument("--dump-filename", required=True)
    write.add_argument("--created-at", required=True)
    write.add_argument("--schema-version", required=True)
    write.add_argument("--pg-dump-version", required=True)
    write.add_argument("--postgres-server-version", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle-dir", required=True)
    verify.add_argument("--allow-staging", action="store_true")

    commit = subparsers.add_parser("commit")
    commit.add_argument("--backup-dir", required=True)
    commit.add_argument("--staging-dir", required=True)
    commit.add_argument("--final-bundle-name", required=True)

    cleanup = subparsers.add_parser("cleanup-staging")
    cleanup.add_argument("--backup-dir", required=True)
    cleanup.add_argument("--staging-dir", required=True)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--backup-dir", required=True)

    container = subparsers.add_parser("check-container")
    container.add_argument("--project-name", required=True)
    container.add_argument("--compose-file", required=True)
    container.add_argument("--expected-image", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "validate-env":
        print(validate_env_path(args.repo_root, args.path))
    elif args.command == "validate-backup-dir":
        print(validate_backup_directory(args.repo_root, args.path))
    elif args.command == "new-stem":
        print(create_stem(args.created_at, args.schema_version))
    elif args.command == "fsync-dump":
        fsync_dump_file(
            Path(args.backup_dir).resolve(),
            Path(args.staging_dir).resolve(),
            args.dump_filename,
        )
    elif args.command == "write-sidecars":
        write_sidecars(
            Path(args.backup_dir).resolve(),
            Path(args.staging_dir).resolve(),
            args.dump_filename,
            args.created_at,
            args.schema_version,
            args.pg_dump_version,
            args.postgres_server_version,
        )
    elif args.command == "verify":
        metadata = verify_bundle(
            Path(args.bundle_dir).resolve(), allow_staging=args.allow_staging
        )
        print(json.dumps(metadata, ensure_ascii=True, sort_keys=True))
    elif args.command == "commit":
        final_dump = commit_bundle(
            Path(args.backup_dir).resolve(),
            Path(args.staging_dir).resolve(),
            args.final_bundle_name,
        )
        print(final_dump)
    elif args.command == "cleanup-staging":
        cleanup_staging(
            Path(args.backup_dir).resolve(), Path(args.staging_dir).resolve()
        )
    elif args.command == "inventory":
        print(
            json.dumps(
                inventory(Path(args.backup_dir).resolve()),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "check-container":
        check_postgres_container(
            json.load(sys.stdin),
            args.project_name,
            Path(args.compose_file),
            args.expected_image,
        )


if __name__ == "__main__":
    try:
        main()
    except ContractError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
