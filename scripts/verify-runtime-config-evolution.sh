#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
git_head="$(git -C "$ROOT_DIR" rev-parse HEAD)"
if [[ ! "$git_head" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Runtime-config evolution source HEAD가 exact commit SHA가 아닙니다.\n' >&2
  exit 1
fi
cd "$ROOT_DIR"

PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  scripts.host_tools.test_runtime_config_evolution

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  printf 'Runtime-config evolution gate에 Docker가 필요합니다.\n' >&2
  exit 1
fi

cleanup_task="${GITHUB_HEAD_REF:-}"
if [[ -z "$cleanup_task" ]]; then
  cleanup_task="$(git -C "$ROOT_DIR" branch --show-current)"
fi
if [[ -z "$cleanup_task" ]]; then
  cleanup_task="runtime-config-evolution-${git_head:0:12}"
fi
if [[ ! "$cleanup_task" =~ ^[A-Za-z0-9._/-]{1,128}$ ]]; then
  printf 'Runtime-config evolution cleanup task 식별자가 유효하지 않습니다.\n' >&2
  exit 1
fi

image_tag="our-ledger-runtime-config:evolution-${git_head:0:12}-$$"
container_name="our-ledger-runtime-config-evolution-$$"
temporary_root="$(mktemp -d)"
runtime_archive="$temporary_root/runtime.tar"
image_created=false
container_created=false

cleanup() {
  local original_status=$?
  local cleanup_status=0

  trap - EXIT HUP INT TERM
  set +e
  if [[ "$container_created" == true ]]; then
    docker rm --force "$container_name" >/dev/null 2>&1 || cleanup_status=1
  fi
  if [[ "$image_created" == true ]]; then
    docker image rm --force "$image_tag" >/dev/null 2>&1 || cleanup_status=1
  fi
  rm -rf -- "$temporary_root"
  if docker container inspect "$container_name" >/dev/null 2>&1 \
    || docker image inspect "$image_tag" >/dev/null 2>&1; then
    printf 'Runtime-config evolution Docker residue가 남았습니다.\n' >&2
    cleanup_status=1
  fi
  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

cleanup_labels=(
  --label io.homeserver.cleanup.environment=development
  --label io.homeserver.cleanup.project=our-ledger
  --label "io.homeserver.cleanup.task=$cleanup_task"
  --label io.homeserver.cleanup.lifecycle=task
  --label io.homeserver.cleanup.retain=false
  --label "io.homeserver.cleanup.git-head=$git_head"
)

docker build \
  --platform linux/arm64 \
  --network none \
  --build-arg "REVISION=$git_head" \
  "${cleanup_labels[@]}" \
  --tag "$image_tag" \
  --file "$ROOT_DIR/runtime-config.Dockerfile" \
  "$ROOT_DIR"
image_created=true

actual_architecture="$(docker image inspect --format '{{.Architecture}}' "$image_tag")"
actual_revision="$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "$image_tag"
)"
if [[ "$actual_architecture" != arm64 || "$actual_revision" != "$git_head" ]]; then
  printf 'Bridge runtime-config image identity가 올바르지 않습니다.\n' >&2
  exit 1
fi

docker create \
  --platform linux/arm64 \
  --name "$container_name" \
  "${cleanup_labels[@]}" \
  "$image_tag" >/dev/null
container_created=true
docker export --output "$runtime_archive" "$container_name"

python3 -B - "$runtime_archive" <<'PY'
import stat
import sys
import tarfile
from pathlib import PurePosixPath

archive = sys.argv[1]
legacy_files = {
    "compose.yaml": 0o600,
    "infra/nginx/nginx.conf": 0o600,
    "scripts/backup-production.sh": 0o700,
    "scripts/bootstrap-production.sh": 0o700,
    "scripts/backup_tools/backup_artifact.py": 0o600,
    "scripts/backup_tools/backup_core.sh": 0o600,
    "scripts/deploy-production.sh": 0o700,
    "scripts/host_tools/deploy_transaction.py": 0o600,
    "scripts/host_tools/fresh_bootstrap_state.py": 0o600,
    "scripts/host_tools/fresh_host_bootstrap.py": 0o600,
    "scripts/host_tools/host_state.py": 0o600,
    "scripts/host_tools/production_deploy.py": 0o600,
    "scripts/host_tools/production_fresh_bootstrap.py": 0o600,
    "scripts/host_tools/production_host.py": 0o600,
    "scripts/monitor-production.sh": 0o700,
    "scripts/production-status.sh": 0o700,
    "scripts/release_tools/release_contract.py": 0o700,
    "scripts/status_tools/monitor_policy.py": 0o600,
    "scripts/status_tools/monitor_worker.py": 0o600,
    "scripts/status_tools/production_status.py": 0o600,
}
legacy_directories = {
    str(parent)
    for relative in legacy_files
    for parent in PurePosixPath(relative).parents
    if str(parent) != "."
}
actual_directories = set()
actual_files = {}
file_members = {}
seen = set()
runtime_root_seen = False

with tarfile.open(archive, "r") as bundle:
    for member in bundle.getmembers():
        path = PurePosixPath(member.name)
        normalized = member.name[:-1] if member.name.endswith("/") else member.name
        if path.is_absolute() or ".." in path.parts or normalized != path.as_posix():
            raise SystemExit("bridge archive contains an unsafe path")
        if not path.parts or path.parts[0] != "runtime":
            continue
        if len(path.parts) == 1:
            if runtime_root_seen or not member.isdir():
                raise SystemExit("bridge runtime root differs")
            runtime_root_seen = True
            continue
        relative = PurePosixPath(*path.parts[1:]).as_posix()
        if relative in seen:
            raise SystemExit("bridge archive contains a duplicate entry")
        seen.add(relative)
        if member.isdir():
            actual_directories.add(relative)
        elif member.isfile():
            actual_files[relative] = stat.S_IMODE(member.mode)
            file_members[relative] = member
        else:
            raise SystemExit("bridge archive contains non-regular material")

    if not runtime_root_seen:
        raise SystemExit("bridge runtime root is missing")
    if actual_directories != legacy_directories:
        raise SystemExit("bridge directory set differs from frozen Legacy V1")
    if actual_files != legacy_files:
        raise SystemExit("bridge file or mode set differs from frozen Legacy V1")
    for forbidden in (
        "runtime-manifest.json",
        "scripts/backup_tools/offsite_backup.py",
        "scripts/offsite-backup-production.sh",
    ):
        if forbidden in actual_files:
            raise SystemExit("bridge contains a future Manifested V2 entry")
    for relative, member in file_members.items():
        source = bundle.extractfile(member)
        if source is None:
            raise SystemExit("bridge file content is unavailable")
        with source:
            payload = source.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise SystemExit("bridge file is too large")
        lowered = PurePosixPath(relative).name.lower()
        if lowered in {".env", "last-success.json", "monitor-state.json"}:
            raise SystemExit("bridge contains state or env material")
        if PurePosixPath(relative).suffix.lower() in {".key", ".pem", ".p12", ".jks", ".dump"}:
            raise SystemExit("bridge contains private or backup material")
        if b"BEGIN PRIVATE KEY" in payload:
            raise SystemExit("bridge contains private key material")
PY

printf 'Runtime-config evolution bridge 검증을 통과했습니다.\n'
