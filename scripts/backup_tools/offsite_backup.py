#!/usr/bin/env python3
"""Encrypted offsite publication for a verified our-ledger backup bundle.

The public CLI deliberately has no path or executable overrides. Tests exercise the
same transaction through ``OffsiteAuthority`` instances rooted in disposable
directories; production always uses the fixed Mac mini authority below.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePath
import re
import signal
import stat
import subprocess
import sys
import uuid
from typing import Any, Callable

from scripts.backup_tools import backup_artifact


FORMAT_VERSION = 1
MARKER_FILENAME = "offsite-last-success.json"
LOCK_FILENAME = ".our-ledger-offsite.lock"
FRESHNESS_GRACE_SECONDS = 8 * 60 * 60
MAX_CONFIG_BYTES = 16 * 1024
PIPELINE_TIMEOUT_SECONDS = 15 * 60

PRODUCTION_BACKUP_DIRECTORY = Path(
    "/Users/homeserver/Server/backups/our-ledger/data"
)
PRODUCTION_CONFIG_PATH = Path(
    "/Users/homeserver/Server/apps/our-ledger/offsite.env"
)
PRODUCTION_STATE_DIRECTORY = Path(
    "/Users/homeserver/Server/apps/our-ledger/offsite-state"
)
PRODUCTION_ICLOUD_ROOT = (
    Path("/Users/homeserver/Library/Mobile Documents/com~apple~CloudDocs")
)
PRODUCTION_AGE_ENTRYPOINT = Path("/opt/homebrew/bin/age")
PRODUCTION_AGE_CANONICAL_PARENT = Path("/opt/homebrew/Cellar/age")
PRODUCTION_TAR_EXECUTABLE = Path("/usr/bin/bsdtar")

CONFIG_KEYS = frozenset({"AGE_RECIPIENT", "ICLOUD_TARGET_DIRECTORY"})
MARKER_KEYS = frozenset(
    {
        "formatVersion",
        "replicatedAt",
        "sourceBundle",
        "sourceCreatedAt",
        "schemaVersion",
        "ciphertextFilename",
        "ciphertextSizeBytes",
        "ciphertextSha256",
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AGE_X25519_RECIPIENT_PATTERN = re.compile(
    r"^age1[023456789acdefghjklmnpqrstuvwxyz]{58}$"
)
UTC_TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class ContractError(RuntimeError):
    """Raised when an authority or publication invariant is not satisfied."""


class LockBusyError(ContractError):
    """Raised when another offsite worker owns the non-blocking lock."""


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


def _private_info(
    path: Path,
    label: str,
    *,
    directory: bool,
    exact_mode: int,
    require_single_link: bool = False,
) -> os.stat_result:
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
        stat.S_IMODE(info.st_mode) == exact_mode,
        f"{label} mode가 owner-only contract와 다릅니다.",
    )
    if require_single_link:
        require(info.st_nlink == 1, f"{label}는 hardlink일 수 없습니다.")
    return info


def _canonical_private_directory(
    repo_root: Path,
    value: Path,
    label: str,
    *,
    outside_repository: bool = True,
) -> Path:
    candidate = _raw_path(str(value), label)
    require(candidate.exists(), f"{label} path가 존재하지 않습니다.")
    _private_info(candidate, label, directory=True, exact_mode=0o700)
    try:
        canonical = candidate.resolve(strict=True)
        canonical_repo = repo_root.resolve(strict=True)
    except OSError as error:
        raise ContractError(f"{label} path를 canonicalize할 수 없습니다.") from error
    if outside_repository:
        require(
            not _is_within(canonical, canonical_repo),
            f"{label}는 repository 밖에 있어야 합니다.",
        )
    return canonical


def _canonical_private_file(repo_root: Path, value: Path, label: str) -> Path:
    candidate = _raw_path(str(value), label)
    require(candidate.exists(), f"{label} path가 존재하지 않습니다.")
    _private_info(
        candidate,
        label,
        directory=False,
        exact_mode=0o600,
        require_single_link=True,
    )
    try:
        canonical = candidate.resolve(strict=True)
        canonical_repo = repo_root.resolve(strict=True)
    except OSError as error:
        raise ContractError(f"{label} path를 canonicalize할 수 없습니다.") from error
    require(
        not _is_within(canonical, canonical_repo),
        f"{label}는 repository 밖에 있어야 합니다.",
    )
    return canonical


def _validate_disjoint_paths(*paths: Path) -> None:
    for index, candidate in enumerate(paths):
        for other in paths[index + 1 :]:
            require(
                not _is_within(candidate, other)
                and not _is_within(other, candidate),
                "offsite authority path는 서로 disjoint여야 합니다.",
            )


def _validate_executable(path: Path, label: str) -> Path:
    candidate = _raw_path(str(path), label)
    try:
        entry_info = candidate.lstat()
        canonical = candidate.resolve(strict=True)
        info = canonical.stat()
    except OSError as error:
        raise ContractError(f"{label} executable authority를 확인할 수 없습니다.") from error
    require(
        stat.S_ISREG(info.st_mode),
        f"{label} executable canonical target이 regular file이 아닙니다.",
    )
    require(
        entry_info.st_uid in {0, os.geteuid()} and info.st_uid in {0, os.geteuid()},
        f"{label} executable owner가 허용되지 않습니다.",
    )
    require(
        (stat.S_ISLNK(entry_info.st_mode) or stat.S_IMODE(entry_info.st_mode) & 0o022 == 0)
        and stat.S_IMODE(info.st_mode) & 0o022 == 0,
        f"{label} executable이 group/other writable입니다.",
    )
    require(os.access(canonical, os.X_OK), f"{label} executable을 실행할 수 없습니다.")
    return canonical


@dataclass(frozen=True)
class OffsiteAuthority:
    repo_root: Path
    backup_directory: Path
    config_path: Path
    state_directory: Path
    icloud_root: Path
    age_entrypoint: Path
    tar_executable: Path
    production: bool = False


@dataclass(frozen=True)
class ResolvedAuthority:
    repo_root: Path
    backup_directory: Path
    config_path: Path
    state_directory: Path
    icloud_root: Path
    target_directory: Path
    age_executable: Path
    tar_executable: Path
    recipient: str


@dataclass(frozen=True)
class SourceBundle:
    path: Path
    name: str
    created_at: str
    schema_version: str
    fingerprint: tuple[tuple[Any, ...], ...]


def production_authority(repo_root: Path) -> OffsiteAuthority:
    return OffsiteAuthority(
        repo_root=repo_root,
        backup_directory=PRODUCTION_BACKUP_DIRECTORY,
        config_path=PRODUCTION_CONFIG_PATH,
        state_directory=PRODUCTION_STATE_DIRECTORY,
        icloud_root=PRODUCTION_ICLOUD_ROOT,
        age_entrypoint=PRODUCTION_AGE_ENTRYPOINT,
        tar_executable=PRODUCTION_TAR_EXECUTABLE,
        production=True,
    )


def _parse_config(path: Path) -> tuple[str, Path]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ContractError("offsite config를 읽을 수 없습니다.") from error
    require(0 < len(content) <= MAX_CONFIG_BYTES, "offsite config size가 잘못됐습니다.")
    require(b"AGE-SECRET-KEY" not in content, "offsite config에 private identity가 있습니다.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("offsite config encoding이 잘못됐습니다.") from error

    values: dict[str, str] = {}
    for line in text.splitlines():
        require(bool(line), "offsite config에는 빈 줄을 사용할 수 없습니다.")
        require("=" in line, "offsite config line 형식이 잘못됐습니다.")
        key, value = line.split("=", 1)
        require(key in CONFIG_KEYS, "offsite config key가 exact contract와 다릅니다.")
        require(key not in values, "offsite config key가 중복됐습니다.")
        require(bool(value) and value == value.strip(), "offsite config value가 잘못됐습니다.")
        require(not _has_control(value), "offsite config value에 control 문자가 있습니다.")
        values[key] = value
    require(set(values) == CONFIG_KEYS, "offsite config field가 exact contract와 다릅니다.")

    recipient = values["AGE_RECIPIENT"]
    require(
        AGE_X25519_RECIPIENT_PATTERN.fullmatch(recipient) is not None,
        "age recipient 형식이 잘못됐습니다.",
    )
    target = _raw_path(values["ICLOUD_TARGET_DIRECTORY"], "iCloud target directory")
    return recipient, target


def _validate_production_constants(authority: OffsiteAuthority) -> None:
    require(authority.backup_directory == PRODUCTION_BACKUP_DIRECTORY, "production backup authority가 고정값과 다릅니다.")
    require(authority.config_path == PRODUCTION_CONFIG_PATH, "production config authority가 고정값과 다릅니다.")
    require(authority.state_directory == PRODUCTION_STATE_DIRECTORY, "production state authority가 고정값과 다릅니다.")
    require(authority.icloud_root == PRODUCTION_ICLOUD_ROOT, "production iCloud authority가 고정값과 다릅니다.")
    require(authority.age_entrypoint == PRODUCTION_AGE_ENTRYPOINT, "production age authority가 고정값과 다릅니다.")
    require(authority.tar_executable == PRODUCTION_TAR_EXECUTABLE, "production tar authority가 고정값과 다릅니다.")


def resolve_authority(authority: OffsiteAuthority, *, include_binaries: bool) -> ResolvedAuthority:
    try:
        repo_root = authority.repo_root.resolve(strict=True)
    except OSError as error:
        raise ContractError("repository root authority를 확인할 수 없습니다.") from error
    require(repo_root.is_dir(), "repository root authority가 directory가 아닙니다.")
    if authority.production:
        _validate_production_constants(authority)

    try:
        backup_directory = backup_artifact.validate_backup_directory_read_only(
            str(repo_root), str(authority.backup_directory)
        )
    except backup_artifact.ContractError as error:
        raise ContractError("local backup authority가 잘못됐습니다.") from error
    config_path = _canonical_private_file(repo_root, authority.config_path, "offsite config")
    state_directory = _canonical_private_directory(
        repo_root, authority.state_directory, "offsite state directory"
    )
    icloud_root = _canonical_private_directory(
        repo_root,
        authority.icloud_root,
        "iCloud root",
    )
    recipient, target_value = _parse_config(config_path)
    target_directory = _canonical_private_directory(
        repo_root, target_value, "iCloud target directory"
    )
    require(target_directory != icloud_root, "iCloud target은 root 자체일 수 없습니다.")
    require(
        _is_within(target_directory, icloud_root),
        "iCloud target이 canonical iCloud root 밖에 있습니다.",
    )
    require(
        target_directory.name == "our-ledger",
        "iCloud target은 project-specific our-ledger directory여야 합니다.",
    )
    _validate_disjoint_paths(
        repo_root,
        backup_directory,
        config_path,
        state_directory,
        target_directory,
    )

    age_executable = authority.age_entrypoint
    tar_executable = authority.tar_executable
    if include_binaries:
        age_executable = _validate_executable(authority.age_entrypoint, "age")
        tar_executable = _validate_executable(authority.tar_executable, "tar")
        if authority.production:
            require(
                _is_within(age_executable, PRODUCTION_AGE_CANONICAL_PARENT),
                "production age executable이 pinned Homebrew Cellar authority 밖에 있습니다.",
            )
            require(age_executable.name == "age", "production age executable identity가 잘못됐습니다.")
            require(
                tar_executable == PRODUCTION_TAR_EXECUTABLE,
                "production tar executable canonical path가 잘못됐습니다.",
            )

    validate_state_entries(state_directory)
    return ResolvedAuthority(
        repo_root=repo_root,
        backup_directory=backup_directory,
        config_path=config_path,
        state_directory=state_directory,
        icloud_root=icloud_root,
        target_directory=target_directory,
        age_executable=age_executable,
        tar_executable=tar_executable,
        recipient=recipient,
    )


def validate_state_entries(state_directory: Path) -> None:
    allowed = {MARKER_FILENAME, LOCK_FILENAME}
    try:
        entries = list(state_directory.iterdir())
    except OSError as error:
        raise ContractError("offsite state directory entry를 확인할 수 없습니다.") from error
    require(
        all(entry.name in allowed for entry in entries),
        "offsite state directory에 예상 밖 entry가 있습니다.",
    )
    for entry in entries:
        _private_info(
            entry,
            "offsite state entry",
            directory=False,
            exact_mode=0o600,
            require_single_link=True,
        )


class OffsiteLock:
    def __init__(self, state_directory: Path) -> None:
        self.path = state_directory / LOCK_FILENAME
        self.descriptor: int | None = None

    def __enter__(self) -> "OffsiteLock":
        existed = os.path.lexists(self.path)
        if existed:
            _private_info(
                self.path,
                "offsite lock",
                directory=False,
                exact_mode=0o600,
                require_single_link=True,
            )
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            info = os.fstat(descriptor)
            require(stat.S_ISREG(info.st_mode), "offsite lock type이 잘못됐습니다.")
            require(info.st_uid == os.geteuid(), "offsite lock owner가 잘못됐습니다.")
            require(stat.S_IMODE(info.st_mode) == 0o600, "offsite lock mode가 잘못됐습니다.")
            require(info.st_nlink == 1, "offsite lock은 hardlink일 수 없습니다.")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise LockBusyError("offsite worker가 이미 실행 중입니다.") from error
        except BaseException:
            if "descriptor" in locals():
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


def _parse_timestamp(value: object, label: str) -> dt.datetime:
    require(type(value) is str and UTC_TIMESTAMP_PATTERN.fullmatch(value) is not None, f"{label} timestamp 형식이 잘못됐습니다.")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ContractError(f"{label} timestamp가 잘못됐습니다.") from error
    return parsed.replace(tzinfo=dt.timezone.utc)


def _format_timestamp(value: dt.datetime) -> str:
    require(value.tzinfo is not None, "clock은 timezone-aware여야 합니다.")
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _safe_direct_name(value: object, label: str) -> str:
    require(type(value) is str and bool(value), f"{label}가 비어 있습니다.")
    require(not _has_control(value), f"{label}에 control 문자가 있습니다.")
    require(PurePath(value).parts == (value,), f"{label}는 direct child 이름이어야 합니다.")
    return value


def _ciphertext_name(source_bundle: str) -> str:
    source_bundle = _safe_direct_name(source_bundle, "source bundle")
    require(source_bundle.endswith(".backup"), "source bundle 확장자가 잘못됐습니다.")
    stem = source_bundle.removesuffix(".backup")
    try:
        backup_artifact.parse_stem(stem)
    except backup_artifact.ContractError as error:
        raise ContractError("source bundle 이름이 backup contract와 다릅니다.") from error
    return f"{stem}.tar.age"


def _open_regular_for_hash(path: Path, label: str, *, exact_mode: int) -> tuple[int, os.stat_result]:
    try:
        before = path.lstat()
        require(not stat.S_ISLNK(before.st_mode), f"{label}는 symlink일 수 없습니다.")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        after = os.fstat(descriptor)
        require(stat.S_ISREG(after.st_mode), f"{label}는 regular file이어야 합니다.")
        require(after.st_uid == os.geteuid(), f"{label} owner가 잘못됐습니다.")
        require(stat.S_IMODE(after.st_mode) == exact_mode, f"{label} mode가 잘못됐습니다.")
        require(after.st_nlink == 1, f"{label}는 hardlink일 수 없습니다.")
        require(
            (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
            f"{label}가 open 중 교체됐습니다.",
        )
        return descriptor, after
    except ContractError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as error:
        if "descriptor" in locals():
            os.close(descriptor)
        raise ContractError(f"{label}를 안전하게 열 수 없습니다.") from error


def _hash_regular_file(path: Path, label: str, *, exact_mode: int = 0o600) -> tuple[int, str, os.stat_result]:
    descriptor, before = _open_regular_for_hash(path, label, exact_mode=exact_mode)
    digest = hashlib.sha256()
    try:
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            f"{label}가 hash 중 변경됐습니다.",
        )
        return after.st_size, digest.hexdigest(), after
    except ContractError:
        raise
    except OSError as error:
        raise ContractError(f"{label} hash를 계산할 수 없습니다.") from error
    finally:
        os.close(descriptor)


def _source_fingerprint(bundle: Path) -> tuple[tuple[Any, ...], ...]:
    try:
        metadata = backup_artifact.verify_bundle(bundle)
    except backup_artifact.ContractError as error:
        raise ContractError("latest local backup bundle 검증에 실패했습니다.") from error
    expected = {
        metadata["dumpFilename"],
        f"{bundle.name.removesuffix('.backup')}.json",
        f"{bundle.name.removesuffix('.backup')}.sha256",
    }
    try:
        entries = sorted(bundle.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise ContractError("latest local backup bundle을 읽을 수 없습니다.") from error
    require({entry.name for entry in entries} == expected, "latest local backup file set이 변경됐습니다.")
    fingerprint: list[tuple[Any, ...]] = []
    for entry in entries:
        size, sha256, info = _hash_regular_file(entry, "local backup source")
        fingerprint.append(
            (
                entry.name,
                info.st_dev,
                info.st_ino,
                size,
                info.st_mtime_ns,
                sha256,
            )
        )
    return tuple(fingerprint)


def select_latest_source(backup_directory: Path) -> SourceBundle:
    current = backup_artifact.inventory(backup_directory)
    require(current["lastSuccessValid"] is True, "latest local backup marker가 유효하지 않습니다.")
    latest = [entry for entry in current["valid"] if entry["isLatest"]]
    require(len(latest) == 1, "latest local backup authority가 정확히 하나가 아닙니다.")
    name = _safe_direct_name(latest[0]["bundleDirectory"], "latest bundle")
    bundle = backup_directory / name
    marker_path = backup_directory / "last-success.json"
    _private_info(
        marker_path,
        "local backup marker",
        directory=False,
        exact_mode=0o600,
        require_single_link=True,
    )
    try:
        local_marker = _load_json_object(marker_path, "local backup marker")
        backup_artifact._validate_marker(local_marker)
    except backup_artifact.ContractError as error:
        raise ContractError("latest local backup marker 검증에 실패했습니다.") from error
    require(
        local_marker["bundleDirectory"] == name,
        "latest local backup marker와 selected bundle이 다릅니다.",
    )
    try:
        metadata = backup_artifact.verify_bundle(bundle)
    except backup_artifact.ContractError as error:
        raise ContractError("latest local backup bundle 검증에 실패했습니다.") from error
    require(
        all(local_marker[key] == metadata[key] for key in backup_artifact.METADATA_KEYS),
        "latest local backup marker와 bundle metadata가 다릅니다.",
    )
    fingerprint = _source_fingerprint(bundle)
    return SourceBundle(
        path=bundle,
        name=name,
        created_at=metadata["createdAt"],
        schema_version=metadata["schemaVersion"],
        fingerprint=fingerprint,
    )


def revalidate_source(source: SourceBundle, backup_directory: Path) -> None:
    latest = select_latest_source(backup_directory)
    require(
        latest.name == source.name
        and latest.created_at == source.created_at
        and latest.schema_version == source.schema_version
        and latest.fingerprint == source.fingerprint,
        "local backup source authority가 처리 중 변경됐습니다.",
    )


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"{label} JSON을 읽을 수 없습니다.") from error
    require(isinstance(value, dict), f"{label} JSON은 object여야 합니다.")
    return value


def validate_marker(value: dict[str, Any]) -> dict[str, Any]:
    require(set(value) == MARKER_KEYS, "offsite marker field가 exact contract와 다릅니다.")
    require(value["formatVersion"] == FORMAT_VERSION, "offsite marker formatVersion이 다릅니다.")
    _parse_timestamp(value["replicatedAt"], "replicatedAt")
    _parse_timestamp(value["sourceCreatedAt"], "sourceCreatedAt")
    source_bundle = _safe_direct_name(value["sourceBundle"], "sourceBundle")
    expected_ciphertext = _ciphertext_name(source_bundle)
    require(
        value["ciphertextFilename"] == expected_ciphertext,
        "offsite marker ciphertext filename이 source와 다릅니다.",
    )
    backup_artifact.validate_schema_version(value["schemaVersion"])
    require(
        type(value["ciphertextSizeBytes"]) is int
        and value["ciphertextSizeBytes"] > 0,
        "offsite marker ciphertext size가 잘못됐습니다.",
    )
    require(
        type(value["ciphertextSha256"]) is str
        and SHA256_PATTERN.fullmatch(value["ciphertextSha256"]) is not None,
        "offsite marker ciphertext SHA-256이 잘못됐습니다.",
    )
    return value


def load_marker(state_directory: Path) -> tuple[dict[str, Any] | None, bytes | None]:
    marker_path = state_directory / MARKER_FILENAME
    if not os.path.lexists(marker_path):
        return None, None
    _private_info(
        marker_path,
        "offsite marker",
        directory=False,
        exact_mode=0o600,
        require_single_link=True,
    )
    try:
        content = marker_path.read_bytes()
    except OSError as error:
        raise ContractError("offsite marker를 읽을 수 없습니다.") from error
    marker = _load_json_object(marker_path, "offsite marker")
    return validate_marker(marker), content


def _validate_final(marker: dict[str, Any], target_directory: Path) -> Path:
    filename = _safe_direct_name(marker["ciphertextFilename"], "ciphertext filename")
    final = target_directory / filename
    size, sha256, _ = _hash_regular_file(final, "offsite ciphertext")
    require(size == marker["ciphertextSizeBytes"], "offsite ciphertext size가 marker와 다릅니다.")
    require(sha256 == marker["ciphertextSha256"], "offsite ciphertext SHA-256이 marker와 다릅니다.")
    return final


def _marker_matches_source(
    marker: dict[str, Any], source: SourceBundle, target_directory: Path
) -> bool:
    _validate_final(marker, target_directory)
    return (
        marker["sourceBundle"] == source.name
        and marker["sourceCreatedAt"] == source.created_at
        and marker["schemaVersion"] == source.schema_version
        and marker["ciphertextFilename"] == _ciphertext_name(source.name)
    )


def _create_exclusive(path: Path, label: str) -> tuple[int, tuple[int, int]]:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode), f"{label} type이 잘못됐습니다.")
        require(info.st_uid == os.geteuid(), f"{label} owner가 잘못됐습니다.")
        require(stat.S_IMODE(info.st_mode) == 0o600, f"{label} mode가 잘못됐습니다.")
        require(info.st_nlink == 1, f"{label}는 hardlink일 수 없습니다.")
        return descriptor, (info.st_dev, info.st_ino)
    except ContractError:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as error:
        if "descriptor" in locals():
            os.close(descriptor)
        raise ContractError(f"{label}를 exclusive 생성할 수 없습니다.") from error


def _fsync_directory(directory: Path) -> None:
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(directory, flags)
        os.fsync(descriptor)
    except OSError as error:
        raise ContractError("offsite directory를 fsync할 수 없습니다.") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unlink_owned(path: Path, identity: tuple[int, int], label: str) -> None:
    if not os.path.lexists(path):
        return
    try:
        info = path.lstat()
    except OSError as error:
        raise ContractError(f"{label} cleanup authority를 확인할 수 없습니다.") from error
    require(not stat.S_ISLNK(info.st_mode) and stat.S_ISREG(info.st_mode), f"{label} cleanup target이 regular file이 아닙니다.")
    require(info.st_uid == os.geteuid(), f"{label} cleanup target owner가 잘못됐습니다.")
    require(stat.S_IMODE(info.st_mode) == 0o600, f"{label} cleanup target mode가 잘못됐습니다.")
    require((info.st_dev, info.st_ino) == identity, f"{label} cleanup target이 교체됐습니다.")
    try:
        path.unlink()
    except OSError as error:
        raise ContractError(f"{label} cleanup에 실패했습니다.") from error


def encrypt_bundle_pipeline(
    source: SourceBundle,
    resolved: ResolvedAuthority,
    destination_descriptor: int,
) -> None:
    tar_process: subprocess.Popen[bytes] | None = None
    age_process: subprocess.Popen[bytes] | None = None
    child_environment = {
        "COPYFILE_DISABLE": "1",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }
    try:
        tar_process = subprocess.Popen(
            [
                str(resolved.tar_executable),
                "-C",
                str(resolved.backup_directory),
                "-cf",
                "-",
                "--",
                source.name,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            env=child_environment,
        )
        require(tar_process.stdout is not None, "tar pipeline stdout이 없습니다.")
        age_process = subprocess.Popen(
            [str(resolved.age_executable), "-r", resolved.recipient],
            stdin=tar_process.stdout,
            stdout=destination_descriptor,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            env=child_environment,
        )
        tar_process.stdout.close()
        try:
            age_return = age_process.wait(timeout=PIPELINE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            _terminate_process(age_process)
            _terminate_process(tar_process)
            raise ContractError("offsite encryption pipeline timeout입니다.") from error
        try:
            tar_return = tar_process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            _terminate_process(tar_process)
            raise ContractError("offsite tar pipeline timeout입니다.") from error
        require(tar_return == 0 and age_return == 0, "offsite encryption pipeline이 실패했습니다.")
    except ContractError:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        if age_process is not None:
            _terminate_process(age_process)
        if tar_process is not None:
            _terminate_process(tar_process)
        raise ContractError("offsite encryption pipeline을 실행할 수 없습니다.") from error


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=2)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
            process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass


def _copy_ciphertext(source: Path, destination_descriptor: int) -> tuple[int, str]:
    source_descriptor, before = _open_regular_for_hash(
        source, "local ciphertext staging", exact_mode=0o600
    )
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            block = os.read(source_descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
            view = memoryview(block)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
        after = os.fstat(source_descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "local ciphertext staging이 copy 중 변경됐습니다.",
        )
        return size, digest.hexdigest()
    except ContractError:
        raise
    except OSError as error:
        raise ContractError("offsite ciphertext copy에 실패했습니다.") from error
    finally:
        os.close(source_descriptor)


def _marker_bytes(marker: dict[str, Any]) -> bytes:
    validate_marker(marker)
    return (
        json.dumps(marker, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_atomic_marker(
    state_directory: Path,
    marker: dict[str, Any],
    previous_content: bytes | None,
    fault: Callable[[str], None],
) -> tuple[int, int]:
    marker_path = state_directory / MARKER_FILENAME
    temporary = state_directory / f".{MARKER_FILENAME}.{uuid.uuid4().hex}.partial"
    descriptor, identity = _create_exclusive(temporary, "offsite marker temp")
    replaced = False
    try:
        content = _marker_bytes(marker)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        fault("before_marker_replace")
        os.replace(temporary, marker_path)
        replaced = True
        marker_info = marker_path.lstat()
        _fsync_directory(state_directory)
        return (marker_info.st_dev, marker_info.st_ino)
    except BaseException as error:
        if descriptor >= 0:
            os.close(descriptor)
        if not replaced:
            _unlink_owned(temporary, identity, "offsite marker temp")
        else:
            try:
                if previous_content is None:
                    marker_info = marker_path.lstat()
                    _unlink_owned(
                        marker_path,
                        (marker_info.st_dev, marker_info.st_ino),
                        "offsite marker rollback",
                    )
                else:
                    rollback_path = state_directory / (
                        f".{MARKER_FILENAME}.{uuid.uuid4().hex}.rollback"
                    )
                    rollback_descriptor, _ = _create_exclusive(
                        rollback_path, "offsite marker rollback temp"
                    )
                    try:
                        view = memoryview(previous_content)
                        while view:
                            written = os.write(rollback_descriptor, view)
                            view = view[written:]
                        os.fsync(rollback_descriptor)
                    finally:
                        os.close(rollback_descriptor)
                    os.replace(rollback_path, marker_path)
                _fsync_directory(state_directory)
            except BaseException as rollback_error:
                raise ContractError("offsite marker rollback에 실패했습니다.") from rollback_error
        raise error


def _restore_previous_marker(
    state_directory: Path,
    current_identity: tuple[int, int],
    previous_content: bytes | None,
) -> None:
    marker_path = state_directory / MARKER_FILENAME
    current_info = _private_info(
        marker_path,
        "offsite marker rollback",
        directory=False,
        exact_mode=0o600,
        require_single_link=True,
    )
    require(
        (current_info.st_dev, current_info.st_ino) == current_identity,
        "offsite marker가 rollback 전에 교체됐습니다.",
    )
    if previous_content is None:
        _unlink_owned(marker_path, current_identity, "offsite marker rollback")
        _fsync_directory(state_directory)
        return

    rollback_path = state_directory / (
        f".{MARKER_FILENAME}.{uuid.uuid4().hex}.rollback"
    )
    rollback_descriptor, rollback_identity = _create_exclusive(
        rollback_path, "offsite marker rollback temp"
    )
    try:
        view = memoryview(previous_content)
        while view:
            written = os.write(rollback_descriptor, view)
            view = view[written:]
        os.fsync(rollback_descriptor)
    except BaseException:
        os.close(rollback_descriptor)
        _unlink_owned(
            rollback_path, rollback_identity, "offsite marker rollback temp"
        )
        raise
    os.close(rollback_descriptor)
    rechecked = marker_path.lstat()
    require(
        (rechecked.st_dev, rechecked.st_ino) == current_identity,
        "offsite marker가 rollback commit 전에 교체됐습니다.",
    )
    os.replace(rollback_path, marker_path)
    _fsync_directory(state_directory)


PipelineRunner = Callable[[SourceBundle, ResolvedAuthority, int], None]
FaultInjector = Callable[[str], None]


def _no_fault(point: str) -> None:
    del point


def _safe_now(now: Callable[[], dt.datetime]) -> dt.datetime:
    value = now()
    require(isinstance(value, dt.datetime) and value.tzinfo is not None, "clock이 timezone-aware가 아닙니다.")
    return value.astimezone(dt.timezone.utc).replace(microsecond=0)


def run_offsite_backup(
    authority: OffsiteAuthority,
    *,
    pipeline_runner: PipelineRunner = encrypt_bundle_pipeline,
    fault: FaultInjector = _no_fault,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
) -> dict[str, Any]:
    resolved = resolve_authority(authority, include_binaries=True)
    marker_path = resolved.state_directory / MARKER_FILENAME

    with OffsiteLock(resolved.state_directory):
        validate_state_entries(resolved.state_directory)
        source = select_latest_source(resolved.backup_directory)
        previous_marker, previous_marker_content = load_marker(resolved.state_directory)
        if previous_marker is not None and _marker_matches_source(
            previous_marker, source, resolved.target_directory
        ):
            return _operation_result("NO_OP", previous_marker)

        final_name = _ciphertext_name(source.name)
        final_path = resolved.target_directory / final_name
        require(
            not os.path.lexists(final_path),
            "offsite final ciphertext collision이 있습니다.",
        )

        token = uuid.uuid4().hex
        staging_path = resolved.state_directory / f".offsite-cipher.{token}.partial"
        partial_path = resolved.target_directory / f".{final_name}.{token}.partial"
        staging_descriptor = -1
        partial_descriptor = -1
        staging_identity: tuple[int, int] | None = None
        partial_identity: tuple[int, int] | None = None
        final_identity: tuple[int, int] | None = None
        marker_identity: tuple[int, int] | None = None
        final_created = False
        marker_committed = False
        try:
            staging_descriptor, staging_identity = _create_exclusive(
                staging_path, "local ciphertext staging"
            )
            pipeline_runner(source, resolved, staging_descriptor)
            fault("before_staging_fsync")
            os.fsync(staging_descriptor)
            staging_info = os.fstat(staging_descriptor)
            require(staging_info.st_size > 0, "local ciphertext staging이 비어 있습니다.")
            os.close(staging_descriptor)
            staging_descriptor = -1
            staging_size, staging_sha256, _ = _hash_regular_file(
                staging_path, "local ciphertext staging"
            )
            require(staging_size > 0, "local ciphertext staging이 비어 있습니다.")
            fault("after_staging_hash")

            partial_descriptor, partial_identity = _create_exclusive(
                partial_path, "iCloud ciphertext partial"
            )
            fault("before_ciphertext_copy")
            copied_size, copied_sha256 = _copy_ciphertext(
                staging_path, partial_descriptor
            )
            fault("before_partial_fsync")
            os.fsync(partial_descriptor)
            os.close(partial_descriptor)
            partial_descriptor = -1
            require(
                copied_size == staging_size and copied_sha256 == staging_sha256,
                "iCloud ciphertext copy가 staging과 다릅니다.",
            )
            partial_size, partial_sha256, _ = _hash_regular_file(
                partial_path, "iCloud ciphertext partial"
            )
            require(
                partial_size == staging_size and partial_sha256 == staging_sha256,
                "iCloud ciphertext partial 검증에 실패했습니다.",
            )
            fault("after_partial_hash")

            revalidate_source(source, resolved.backup_directory)
            fault("before_final_rename")
            require(
                not os.path.lexists(final_path),
                "offsite final ciphertext collision이 발생했습니다.",
            )
            os.rename(partial_path, final_path)
            final_created = True
            final_identity = partial_identity
            partial_identity = None
            _fsync_directory(resolved.target_directory)
            fault("after_final_rename")

            final_size, final_sha256, final_info = _hash_regular_file(
                final_path, "offsite final ciphertext"
            )
            require(
                final_size == staging_size and final_sha256 == staging_sha256,
                "offsite final ciphertext 검증에 실패했습니다.",
            )
            require(
                final_identity == (final_info.st_dev, final_info.st_ino),
                "offsite final ciphertext가 publish 중 교체됐습니다.",
            )
            revalidate_source(source, resolved.backup_directory)
            fault("after_final_verify")

            marker = {
                "formatVersion": FORMAT_VERSION,
                "replicatedAt": _format_timestamp(_safe_now(now)),
                "sourceBundle": source.name,
                "sourceCreatedAt": source.created_at,
                "schemaVersion": source.schema_version,
                "ciphertextFilename": final_name,
                "ciphertextSizeBytes": final_size,
                "ciphertextSha256": final_sha256,
            }
            marker_identity = _write_atomic_marker(
                resolved.state_directory,
                marker,
                previous_marker_content,
                fault,
            )
            marker_committed = True
            _unlink_owned(staging_path, staging_identity, "local ciphertext staging")
            _fsync_directory(resolved.state_directory)
            return _operation_result("REPLICATED", marker)
        except BaseException as error:
            if staging_descriptor >= 0:
                os.close(staging_descriptor)
            if partial_descriptor >= 0:
                os.close(partial_descriptor)
            cleanup_errors: list[BaseException] = []
            if marker_committed and marker_identity is not None:
                try:
                    _restore_previous_marker(
                        resolved.state_directory,
                        marker_identity,
                        previous_marker_content,
                    )
                    marker_committed = False
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            for path, identity, label in (
                (partial_path, partial_identity, "iCloud ciphertext partial"),
                (staging_path, staging_identity, "local ciphertext staging"),
            ):
                if identity is not None:
                    try:
                        _unlink_owned(path, identity, label)
                    except BaseException as cleanup_error:
                        cleanup_errors.append(cleanup_error)
            if final_created and not marker_committed and final_identity is not None:
                try:
                    _unlink_owned(final_path, final_identity, "offsite final ciphertext")
                    _fsync_directory(resolved.target_directory)
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                raise ContractError("offsite transaction cleanup에 실패했습니다.") from cleanup_errors[0]
            if isinstance(error, ContractError):
                raise
            if isinstance(error, OSError):
                raise ContractError("offsite publication filesystem operation이 실패했습니다.") from error
            raise


def _operation_result(result: str, marker: dict[str, Any]) -> dict[str, Any]:
    require(result in {"REPLICATED", "NO_OP"}, "offsite operation result가 잘못됐습니다.")
    return {
        "formatVersion": FORMAT_VERSION,
        "operation": "encrypted-offsite-backup",
        "result": result,
        "replicatedAt": marker["replicatedAt"],
        "sourceCreatedAt": marker["sourceCreatedAt"],
        "schemaVersion": marker["schemaVersion"],
        "ciphertextSizeBytes": marker["ciphertextSizeBytes"],
    }


def offsite_status(
    authority: OffsiteAuthority,
    *,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
) -> dict[str, Any]:
    resolved = resolve_authority(authority, include_binaries=False)
    observed_at = _safe_now(now)
    marker_path = resolved.state_directory / MARKER_FILENAME
    if not os.path.lexists(marker_path):
        return _status_result(observed_at, "MISSING", None, None)
    try:
        marker, _ = load_marker(resolved.state_directory)
        require(marker is not None, "offsite marker가 없습니다.")
        _validate_final(marker, resolved.target_directory)
        replicated_at = _parse_timestamp(marker["replicatedAt"], "replicatedAt")
        require(replicated_at <= observed_at, "offsite marker가 future timestamp입니다.")
        age_seconds = int((observed_at - replicated_at).total_seconds())
        freshness = "FRESH" if age_seconds <= FRESHNESS_GRACE_SECONDS else "STALE"
        return _status_result(
            observed_at,
            freshness,
            age_seconds,
            marker["replicatedAt"],
        )
    except ContractError:
        return _status_result(observed_at, "INVALID", None, None)


def _status_result(
    observed_at: dt.datetime,
    state: str,
    age_seconds: int | None,
    replicated_at: str | None,
) -> dict[str, Any]:
    require(state in {"MISSING", "INVALID", "FRESH", "STALE"}, "offsite status state가 잘못됐습니다.")
    return {
        "formatVersion": FORMAT_VERSION,
        "observedAt": _format_timestamp(observed_at),
        "state": state,
        "replicatedAt": replicated_at,
        "ageSeconds": age_seconds,
        "graceSeconds": FRESHNESS_GRACE_SECONDS,
    }


def _parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="our-ledger encrypted offsite backup worker"
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run", help="latest verified local backup을 encrypted offsite로 게시")
    subcommands.add_parser("status", help="offsite marker freshness를 read-only로 확인")
    return result


def main() -> None:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    authority = production_authority(repo_root)
    try:
        if args.command == "run":
            result = run_offsite_backup(authority)
        else:
            result = offsite_status(authority)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    except LockBusyError as error:
        print("encrypted offsite backup worker가 이미 실행 중입니다.", file=sys.stderr)
        raise SystemExit(75) from error
    except (ContractError, OSError, ValueError) as error:
        print("encrypted offsite backup contract를 실행할 수 없습니다.", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
