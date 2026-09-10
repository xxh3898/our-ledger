"""Full CI current-run API/Web test image artifact authority.

The GitHub artifact transport is deliberately not an image authority.  This
module binds the archive bytes and the loaded image to the current checkout,
tree, workflow run, Dockerfile, effective dockerignore, image family and OCI
labels.  It uses only the Python standard library and the local Docker CLI.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_tools import docker_cache  # noqa: E402


REPOSITORY = "xxh3898/our-ledger"
PLATFORM = "linux/amd64"
OCI_SOURCE = "https://github.com/xxh3898/our-ledger"
FORMAT_VERSION = 1
ARCHIVE_NAME = "image.tar.gz"
MANIFEST_NAME = "manifest.json"
ARTIFACT_FORMAT = "docker-save+gzip-v1"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200_000
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
HEX256 = re.compile(r"[0-9a-f]{64}")
RUN_ID = re.compile(r"[1-9][0-9]*")
TARGET_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:+-]{0,254}")
CONSUMERS = {
    "api": {"production-bootstrap", "fresh-host-bootstrap", "backup-restore", "observability"},
    "web": {"fresh-host-bootstrap", "observability"},
}
MANIFEST_KEYS = {
    "formatVersion", "artifactFormat", "repository", "workflowRef", "workflowRunId",
    "runAttempt", "eventName", "githubSha", "prHeadSha", "prBaseSha", "checkoutSha",
    "sourceTreeSha", "imageFamily", "platform", "dockerfilePath", "dockerfileSha256",
    "dockerignorePath", "dockerignoreSha256", "archiveName", "archiveSize",
    "archiveSha256", "imageReference", "imageId", "imageOs", "imageArchitecture",
    "imageConfigDigest", "ociSource", "ociRevision", "ociVersion", "cacheMode", "producerJob",
}


class ArtifactError(ValueError):
    """The artifact does not prove the required current-run image authority."""


@dataclass(frozen=True)
class Authority:
    repository: str
    workflow_ref: str
    run_id: str
    run_attempt: int
    event_name: str
    github_sha: str
    pr_head_sha: str
    pr_base_sha: str
    checkout_sha: str
    source_tree_sha: str
    family: str
    platform: str
    dockerfile_path: str
    dockerfile_sha256: str
    dockerignore_path: str
    dockerignore_sha256: str
    cache_mode: str


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular_file(path: Path, root: Path) -> None:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ArtifactError("artifact authority file is unavailable") from error
    if path.is_symlink() or not path.is_file() or not resolved.is_relative_to(root.resolve()):
        raise ArtifactError("artifact authority file is not a regular repository file")


def _hash_file(path: Path, *, maximum: int | None = None) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise ArtifactError("artifact file must be regular")
    size = path.stat().st_size
    if size <= 0 or (maximum is not None and size > maximum):
        raise ArtifactError("artifact file size is outside the accepted boundary")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return size, digest.hexdigest()


def _git(root: Path, revision: str) -> str:
    try:
        value = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", revision],
            check=True, capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise ArtifactError("current checkout identity is unavailable") from error
    if not SHA.fullmatch(value):
        raise ArtifactError("current checkout identity is not an exact SHA")
    return value


def _environment_sha(environment: Mapping[str, str], key: str, *, empty: bool = False) -> str:
    value = environment.get(key, "")
    if (empty and value == "") or SHA.fullmatch(value):
        return value
    raise ArtifactError(f"{key} is not an exact SHA")


def effective_dockerignore(family: str, root: Path = ROOT) -> Path:
    if family not in docker_cache.DOCKERFILES:
        raise ArtifactError("unknown test image family")
    dockerfile = root / docker_cache.DOCKERFILES[family]
    specific = Path(str(dockerfile) + ".dockerignore")
    return specific if specific.exists() else root / ".dockerignore"


def authority(family: str, environment: Mapping[str, str], root: Path = ROOT) -> Authority:
    if family not in docker_cache.DOCKERFILES:
        raise ArtifactError("unknown test image family")
    cache_mode = docker_cache.event_mode(environment)
    if cache_mode not in {"gha-read", "gha-write"}:
        raise ArtifactError("shared test images are disabled for this workflow authority")
    requested_cache = environment.get("CI_DOCKER_CACHE_MODE", "")
    if requested_cache != cache_mode:
        raise ArtifactError("test image cache mode differs from the workflow authority")
    run_id = environment.get("GITHUB_RUN_ID", "")
    attempt = environment.get("GITHUB_RUN_ATTEMPT", "")
    if not RUN_ID.fullmatch(run_id) or not RUN_ID.fullmatch(attempt):
        raise ArtifactError("workflow run identity is invalid")
    event_name = environment.get("GITHUB_EVENT_NAME", "")
    pr_head = _environment_sha(environment, "CI_PR_HEAD_SHA", empty=event_name == "push")
    pr_base = _environment_sha(environment, "CI_PR_BASE_SHA", empty=event_name == "push")
    if event_name == "pull_request" and (not pr_head or not pr_base):
        raise ArtifactError("PR audit SHAs are required")
    github_sha = _environment_sha(environment, "GITHUB_SHA")
    checkout = _git(root, "HEAD")
    if checkout != github_sha:
        raise ArtifactError("checked-out source differs from the workflow SHA")
    tree = _git(root, "HEAD^{tree}")
    dockerfile = root / docker_cache.DOCKERFILES[family]
    dockerignore = effective_dockerignore(family, root)
    for path in (dockerfile, dockerignore):
        _regular_file(path, root)
    return Authority(
        repository=environment.get("GITHUB_REPOSITORY", ""),
        workflow_ref=environment.get("GITHUB_WORKFLOW_REF", ""),
        run_id=run_id,
        run_attempt=int(attempt),
        event_name=event_name,
        github_sha=github_sha,
        pr_head_sha=pr_head,
        pr_base_sha=pr_base,
        checkout_sha=checkout,
        source_tree_sha=tree,
        family=family,
        platform=PLATFORM,
        dockerfile_path=dockerfile.relative_to(root).as_posix(),
        dockerfile_sha256=_sha256_bytes(dockerfile.read_bytes()),
        dockerignore_path=dockerignore.relative_to(root).as_posix(),
        dockerignore_sha256=_sha256_bytes(dockerignore.read_bytes()),
        cache_mode=cache_mode,
    )


def canonical_reference(family: str, checkout_sha: str) -> str:
    if family not in docker_cache.DOCKERFILES or not SHA.fullmatch(checkout_sha):
        raise ArtifactError("invalid canonical test image identity")
    return f"our-ledger-ci-test-{family}:{checkout_sha}"


def expected_labels(identity: Authority) -> dict[str, str]:
    return {
        "io.homeserver.cleanup.environment": "development",
        "io.homeserver.cleanup.project": "our-ledger",
        "io.homeserver.cleanup.task": "issue-124-exact-head-test-images",
        "io.homeserver.cleanup.lifecycle": "task",
        "io.homeserver.cleanup.retain": "false",
        "io.homeserver.cleanup.git-head": identity.checkout_sha,
        "org.opencontainers.image.source": OCI_SOURCE,
        "org.opencontainers.image.revision": identity.checkout_sha,
        "org.opencontainers.image.version": identity.checkout_sha,
        "io.github.xxh3898.our-ledger.ci.image-family": identity.family,
        "io.github.xxh3898.our-ledger.ci.source-tree": identity.source_tree_sha,
    }


def _inspect(reference: str, environment: Mapping[str, str]) -> dict:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", reference], env=dict(environment), check=True,
            capture_output=True, timeout=30,
        )
        value = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError("Docker image inspection failed") from error
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ArtifactError("Docker image inspection shape differs")
    return value[0]


def _validate_inspection(value: dict, identity: Authority, expected_id: str | None = None) -> str:
    image_id = value.get("Id")
    if not isinstance(image_id, str) or not SHA256.fullmatch(image_id):
        raise ArtifactError("Docker image ID is invalid")
    if expected_id is not None and image_id != expected_id:
        raise ArtifactError("loaded Docker image ID differs from the manifest")
    if value.get("Os") != "linux" or value.get("Architecture") != "amd64":
        raise ArtifactError("Docker image platform differs")
    config = value.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        raise ArtifactError("Docker image labels are unavailable")
    if any(labels.get(key) != expected for key, expected in expected_labels(identity).items()):
        raise ArtifactError("Docker image authority labels differ")
    return image_id


def _remove_image(reference: str, environment: Mapping[str, str], *, required: bool) -> None:
    result = subprocess.run(
        ["docker", "image", "rm", reference], env=dict(environment), check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
    )
    if required and result.returncode != 0:
        raise ArtifactError("test image cleanup failed")


def _image_exists(reference: str, environment: Mapping[str, str]) -> bool:
    return subprocess.run(
        ["docker", "image", "inspect", reference], env=dict(environment), check=False,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
    ).returncode == 0


def _prepare_output(directory: Path) -> None:
    if directory.is_symlink():
        raise ArtifactError("artifact output directory cannot be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir() or any(directory.iterdir()):
        raise ArtifactError("artifact output directory must be empty")


def _save_image(reference: str, archive: Path, environment: Mapping[str, str]) -> None:
    with archive.open("xb") as destination:
        save = subprocess.Popen(
            ["docker", "save", reference], env=dict(environment), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert save.stdout is not None
        compress = subprocess.run(
            ["gzip", "-1", "-n"], env=dict(environment), stdin=save.stdout, stdout=destination,
            stderr=subprocess.DEVNULL, check=False,
        )
        save.stdout.close()
        save_status = save.wait(timeout=300)
    if save_status != 0 or compress.returncode != 0:
        archive.unlink(missing_ok=True)
        raise ArtifactError("Docker image archive creation failed")


def manifest(
    identity: Authority,
    *,
    archive_size: int,
    archive_sha256: str,
    image_id: str,
    image_config_digest: str | None = None,
) -> dict:
    reference = canonical_reference(identity.family, identity.checkout_sha)
    return {
        "formatVersion": FORMAT_VERSION,
        "artifactFormat": ARTIFACT_FORMAT,
        "repository": identity.repository,
        "workflowRef": identity.workflow_ref,
        "workflowRunId": identity.run_id,
        "runAttempt": identity.run_attempt,
        "eventName": identity.event_name,
        "githubSha": identity.github_sha,
        "prHeadSha": identity.pr_head_sha,
        "prBaseSha": identity.pr_base_sha,
        "checkoutSha": identity.checkout_sha,
        "sourceTreeSha": identity.source_tree_sha,
        "imageFamily": identity.family,
        "platform": identity.platform,
        "dockerfilePath": identity.dockerfile_path,
        "dockerfileSha256": identity.dockerfile_sha256,
        "dockerignorePath": identity.dockerignore_path,
        "dockerignoreSha256": identity.dockerignore_sha256,
        "archiveName": ARCHIVE_NAME,
        "archiveSize": archive_size,
        "archiveSha256": archive_sha256,
        "imageReference": reference,
        "imageId": image_id,
        "imageConfigDigest": image_config_digest or image_id,
        "imageOs": "linux",
        "imageArchitecture": "amd64",
        "ociSource": OCI_SOURCE,
        "ociRevision": identity.checkout_sha,
        "ociVersion": identity.checkout_sha,
        "cacheMode": identity.cache_mode,
        "producerJob": "test-images",
    }


def _write_manifest(path: Path, value: dict) -> None:
    payload = (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ArtifactError("artifact manifest is too large")
    path.write_bytes(payload)
    path.chmod(0o600)


def produce(family: str, output_directory: Path, environment: Mapping[str, str], root: Path = ROOT) -> None:
    identity = authority(family, environment, root)
    if environment.get("GITHUB_JOB") != "test-images":
        raise ArtifactError("only the test-images producer may create the artifact")
    _prepare_output(output_directory)
    reference = canonical_reference(family, identity.checkout_sha)
    if _image_exists(reference, environment):
        raise ArtifactError("canonical test image tag already exists")
    labels = [item for pair in expected_labels(identity).items() for item in ("--label", "=".join(pair))]
    arguments = [
        "--progress", "plain", "--pull", "--platform", PLATFORM, *labels,
        "--tag", reference, "--file", str(root / identity.dockerfile_path), str(root),
    ]
    archive = output_directory / ARCHIVE_NAME
    built = False
    try:
        if docker_cache.build_image(family, arguments, environment, root) != 0:
            raise ArtifactError("canonical test image build failed")
        built = True
        image_id = _validate_inspection(_inspect(reference, environment), identity)
        _save_image(reference, archive, environment)
        archive_size, archive_sha = _hash_file(archive, maximum=MAX_ARCHIVE_BYTES)
        config_digest = _validate_docker_archive(archive, reference, image_id)
        _write_manifest(
            output_directory / MANIFEST_NAME,
            manifest(
                identity,
                archive_size=archive_size,
                archive_sha256=archive_sha,
                image_id=image_id,
                image_config_digest=config_digest,
            ),
        )
    finally:
        if built:
            _remove_image(reference, environment, required=True)


class _NoDuplicateObject(dict):
    pass


def _object_pairs(pairs: list[tuple[str, object]]) -> dict:
    value: dict[str, object] = _NoDuplicateObject()
    for key, item in pairs:
        if key in value:
            raise ArtifactError("artifact manifest contains a duplicate key")
        value[key] = item
    return value


def _load_strict_json(path: Path) -> dict:
    size, _ = _hash_file(path, maximum=MAX_MANIFEST_BYTES)
    if size > MAX_MANIFEST_BYTES:
        raise ArtifactError("artifact manifest is too large")
    try:
        value = json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError("artifact manifest is malformed") from error
    if type(value) is not _NoDuplicateObject or set(value) != MANIFEST_KEYS:
        raise ArtifactError("artifact manifest schema differs")
    return value


def _string(value: object, pattern: re.Pattern[str] | None = None, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not empty) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ArtifactError("artifact manifest string is invalid")
    if value and pattern is not None and not pattern.fullmatch(value):
        raise ArtifactError("artifact manifest string has an invalid format")
    return value


def validate_manifest(value: dict, identity: Authority, archive: Path) -> tuple[str, str]:
    if type(value.get("formatVersion")) is not int or value["formatVersion"] != FORMAT_VERSION:
        raise ArtifactError("artifact manifest version differs")
    if type(value.get("runAttempt")) is not int or value["runAttempt"] != identity.run_attempt:
        raise ArtifactError("artifact run attempt differs")
    if type(value.get("archiveSize")) is not int or not 0 < value["archiveSize"] <= MAX_ARCHIVE_BYTES:
        raise ArtifactError("artifact archive size is invalid")
    expected = manifest(
        identity,
        archive_size=value["archiveSize"],
        archive_sha256=_string(value.get("archiveSha256"), HEX256),
        image_id=_string(value.get("imageId"), SHA256),
        image_config_digest=_string(value.get("imageConfigDigest"), SHA256),
    )
    for key, item in expected.items():
        if value.get(key) != item:
            raise ArtifactError(f"artifact manifest {key} differs")
    actual_size, actual_sha = _hash_file(archive, maximum=MAX_ARCHIVE_BYTES)
    if actual_size != value["archiveSize"] or actual_sha != value["archiveSha256"]:
        raise ArtifactError("artifact archive bytes differ from the manifest")
    return value["imageId"], value["imageConfigDigest"]


def _safe_tar_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name) and not name.startswith("/") and "\\" not in name
        and not any(ord(char) < 32 or ord(char) == 127 for char in name)
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _strict_embedded_json(payload: bytes) -> object:
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError("Docker archive metadata is malformed") from error


def _validate_docker_archive(
    archive: Path,
    reference: str,
    image_id: str,
    expected_config_digest: str | None = None,
) -> str:
    expected_hex = image_id.removeprefix("sha256:")
    names: set[str] = set()
    total = 0
    try:
        with tarfile.open(archive, mode="r:gz") as saved:
            members = saved.getmembers()
            if not 1 <= len(members) <= MAX_ARCHIVE_MEMBERS:
                raise ArtifactError("Docker archive member count is invalid")
            for member in members:
                if not _safe_tar_name(member.name) or member.name in names or not (member.isfile() or member.isdir()):
                    raise ArtifactError("Docker archive contains an unsafe member")
                names.add(member.name)
                total += member.size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ArtifactError("Docker archive expands beyond the accepted boundary")
            manifest_member = saved.getmember("manifest.json")
            stream = saved.extractfile(manifest_member)
            if stream is None or manifest_member.size > MAX_MANIFEST_BYTES:
                raise ArtifactError("Docker archive manifest is unavailable")
            embedded = _strict_embedded_json(stream.read())
            if not isinstance(embedded, list) or len(embedded) != 1 or type(embedded[0]) is not _NoDuplicateObject:
                raise ArtifactError("Docker archive must contain exactly one image")
            entry = embedded[0]
            if set(entry) != {"Config", "RepoTags", "Layers"}:
                raise ArtifactError("Docker archive manifest schema differs")
            if entry.get("RepoTags") != [reference] or not isinstance(entry.get("Layers"), list) or not entry["Layers"]:
                raise ArtifactError("Docker archive image reference or layers differ")
            config = entry.get("Config")
            if not isinstance(config, str) or config not in names:
                raise ArtifactError("Docker archive config is unavailable")
            config_match = re.fullmatch(r"(?:blobs/sha256/)?([0-9a-f]{64})(?:\.json)?", config)
            if config_match is None:
                raise ArtifactError("Docker archive config digest is invalid")
            config_digest = "sha256:" + config_match.group(1)
            config_stream = saved.extractfile(config)
            if config_stream is None or _sha256_bytes(config_stream.read()) != config_match.group(1):
                raise ArtifactError("Docker archive config bytes differ from its digest")
            if expected_config_digest is not None and config_digest != expected_config_digest:
                raise ArtifactError("Docker archive config digest differs from the manifest")
            if image_id != config_digest:
                image_blob = f"blobs/sha256/{expected_hex}"
                if image_blob not in names or "index.json" not in names:
                    raise ArtifactError("Docker archive image index does not correspond to the image ID")
                image_stream = saved.extractfile(image_blob)
                index_stream = saved.extractfile("index.json")
                if image_stream is None or index_stream is None or _sha256_bytes(image_stream.read()) != expected_hex:
                    raise ArtifactError("Docker archive image index bytes differ from the image ID")
                index = _strict_embedded_json(index_stream.read())
                descriptors = index.get("manifests") if isinstance(index, dict) else None
                if not isinstance(descriptors, list) or len(descriptors) != 1 or not isinstance(descriptors[0], dict):
                    raise ArtifactError("Docker archive top-level index differs")
                descriptor = descriptors[0]
                annotations = descriptor.get("annotations")
                archive_reference = None if not isinstance(annotations, dict) else (
                    annotations.get("io.containerd.image.name")
                    or annotations.get("org.opencontainers.image.ref.name")
                )
                if descriptor.get("digest") != image_id or archive_reference not in {reference, f"docker.io/library/{reference}"}:
                    raise ArtifactError("Docker archive top-level index does not select the expected image")
            if any(not isinstance(layer, str) or layer not in names for layer in entry["Layers"]):
                raise ArtifactError("Docker archive layer inventory differs")
            return config_digest
    except (OSError, tarfile.TarError, KeyError) as error:
        raise ArtifactError("Docker archive cannot be validated") from error


def _validate_artifact_directory(directory: Path) -> tuple[Path, Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise ArtifactError("artifact directory is unavailable")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != {ARCHIVE_NAME, MANIFEST_NAME} or len(entries) != 2:
        raise ArtifactError("artifact directory must contain exactly the manifest and archive")
    archive, authority_file = directory / ARCHIVE_NAME, directory / MANIFEST_NAME
    if any(path.is_symlink() or not path.is_file() for path in (archive, authority_file)):
        raise ArtifactError("artifact directory contains a non-regular file")
    return archive, authority_file


def _load_image(archive: Path, environment: Mapping[str, str]) -> None:
    decompress = subprocess.Popen(
        ["gzip", "-d", "-c", str(archive)], env=dict(environment), stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert decompress.stdout is not None
    loaded = subprocess.run(
        ["docker", "load"], env=dict(environment), stdin=decompress.stdout,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    decompress.stdout.close()
    decompression_status = decompress.wait(timeout=300)
    if decompression_status != 0 or loaded.returncode != 0:
        raise ArtifactError("Docker image archive import failed")


def consume(
    family: str,
    artifact_directory: Path,
    target_reference: str,
    environment: Mapping[str, str],
    root: Path = ROOT,
) -> None:
    identity = authority(family, environment, root)
    if environment.get("GITHUB_JOB") not in CONSUMERS[family]:
        raise ArtifactError("workflow job is not an allowed image consumer")
    if not TARGET_TAG.fullmatch(target_reference) or target_reference.startswith("-") or "@" in target_reference:
        raise ArtifactError("consumer image tag is invalid")
    archive, authority_file = _validate_artifact_directory(artifact_directory)
    value = _load_strict_json(authority_file)
    expected_id, expected_config = validate_manifest(value, identity, archive)
    canonical = canonical_reference(family, identity.checkout_sha)
    _validate_docker_archive(archive, canonical, expected_id, expected_config)
    if _image_exists(canonical, environment) or _image_exists(target_reference, environment):
        raise ArtifactError("consumer image tag already exists")
    loaded = False
    tagged = False
    adopted = False
    try:
        _load_image(archive, environment)
        loaded = True
        _validate_inspection(_inspect(canonical, environment), identity, expected_id)
        subprocess.run(
            ["docker", "image", "tag", canonical, target_reference], env=dict(environment),
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        tagged = True
        _validate_inspection(_inspect(target_reference, environment), identity, expected_id)
        _remove_image(canonical, environment, required=True)
        loaded = False
        adopted = True
    except (OSError, subprocess.SubprocessError) as error:
        raise ArtifactError("Docker image adoption failed") from error
    finally:
        if loaded:
            _remove_image(canonical, environment, required=False)
        if tagged and not adopted:
            _remove_image(target_reference, environment, required=False)


def main() -> int:
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "produce":
            produce(sys.argv[2], Path(sys.argv[3]), os.environ)
            print(f"current-run test image artifact created: {sys.argv[2]}")
            return 0
        if len(sys.argv) == 5 and sys.argv[1] == "consume":
            consume(sys.argv[2], Path(sys.argv[3]), sys.argv[4], os.environ)
            print(f"current-run test image artifact adopted: {sys.argv[2]}")
            return 0
    except (ArtifactError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Usage: test_image_artifact.py produce <api|web> <directory> | consume <api|web> <directory> <tag>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
