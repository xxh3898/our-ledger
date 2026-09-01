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
temporary_root="$(cd "$temporary_root" && pwd -P)"
runtime_archive="$temporary_root/runtime.tar"
runtime_dir="$temporary_root/runtime"
host_root="$temporary_root/host"
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
actual_version="$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' \
    "$image_tag"
)"
actual_source="$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.source" }}' \
    "$image_tag"
)"
actual_project="$(
  docker image inspect \
    --format '{{ index .Config.Labels "io.chochiho.runtime-config.project" }}' \
    "$image_tag"
)"
if [[ "$actual_architecture" != arm64 \
  || "$actual_revision" != "$git_head" \
  || "$actual_version" != "$git_head" \
  || "$actual_source" != https://github.com/xxh3898/our-ledger \
  || "$actual_project" != our-ledger ]]; then
  printf 'Manifested Runtime V2 image identity가 올바르지 않습니다.\n' >&2
  exit 1
fi

docker create \
  --platform linux/arm64 \
  --name "$container_name" \
  "${cleanup_labels[@]}" \
  "$image_tag" >/dev/null
container_created=true
docker export --output "$runtime_archive" "$container_name"

PYTHONDONTWRITEBYTECODE=1 python3 -B - \
  "$runtime_archive" \
  "$runtime_dir" \
  "$host_root" \
  "$git_head" <<'PY'
import hashlib
import sys
from pathlib import Path

from scripts.host_tools import host_state, production_deploy

archive = Path(sys.argv[1])
runtime = Path(sys.argv[2])
host_root = Path(sys.argv[3])
revision = sys.argv[4]
expected_files = {
    "compose.yaml": 0o600,
    "infra/nginx/nginx.conf": 0o600,
    "scripts/backup-production.sh": 0o700,
    "scripts/backup_tools/backup_artifact.py": 0o600,
    "scripts/backup_tools/backup_core.sh": 0o600,
    "scripts/backup_tools/offsite_backup.py": 0o600,
    "scripts/bootstrap-production.sh": 0o700,
    "scripts/deploy-production.sh": 0o700,
    "scripts/host_tools/deploy_transaction.py": 0o600,
    "scripts/host_tools/fresh_bootstrap_state.py": 0o600,
    "scripts/host_tools/fresh_host_bootstrap.py": 0o600,
    "scripts/host_tools/host_state.py": 0o600,
    "scripts/host_tools/production_deploy.py": 0o600,
    "scripts/host_tools/production_fresh_bootstrap.py": 0o600,
    "scripts/host_tools/production_host.py": 0o600,
    "scripts/monitor-production.sh": 0o700,
    "scripts/offsite-backup-production.sh": 0o700,
    "scripts/production-status.sh": 0o700,
    "scripts/release_tools/release_contract.py": 0o700,
    "scripts/status_tools/monitor_policy.py": 0o600,
    "scripts/status_tools/monitor_worker.py": 0o600,
    "scripts/status_tools/production_status.py": 0o600,
}
expected_directories = {
    "infra",
    "infra/nginx",
    "scripts",
    "scripts/backup_tools",
    "scripts/host_tools",
    "scripts/release_tools",
    "scripts/status_tools",
}
manifest_bytes = Path("runtime-manifest.json").read_bytes()
manifest_profile = host_state.parse_runtime_manifest(manifest_bytes)
if manifest_profile.file_modes != expected_files:
    raise SystemExit("repository V2 manifest payload differs")
if manifest_profile.directories != expected_directories:
    raise SystemExit("repository V2 manifest directory set differs")

production_deploy._extract_verified_runtime(archive, runtime)
extracted_profile = host_state._validate_release(runtime)
if extracted_profile.format_version != 2:
    raise SystemExit("exported runtime is not Manifested V2")
if extracted_profile.file_modes != expected_files:
    raise SystemExit("exported V2 payload differs")
if extracted_profile.directories != expected_directories:
    raise SystemExit("exported V2 directory set differs")
if (runtime / host_state.RUNTIME_MANIFEST).read_bytes() != manifest_bytes:
    raise SystemExit("exported V2 manifest bytes differ")

source_hash = host_state.release_content_sha256(runtime)
paths = host_state.HostPaths(host_root)
host_state.initialize_layout(paths)
runtime_digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
with host_state.OperationLock(paths) as lock:
    identity = host_state.stage_release(
        paths,
        lock,
        runtime,
        application_revision=revision,
        runtime_config_digest=runtime_digest,
        runtime_config_revision=revision,
    )
    host_state.begin_pending(paths, lock, identity)
    host_state.commit_pending(paths, lock)
    state = host_state.inspect_state(paths, lock)

current = paths.releases / identity.release_name
current_profile = host_state._validate_release(current)
if current_profile != extracted_profile:
    raise SystemExit("staged V2 profile differs after re-read")
if host_state.release_content_sha256(current) != source_hash:
    raise SystemExit("staged V2 content hash differs after re-read")
if identity.runtime_config_content_sha256 != source_hash:
    raise SystemExit("staged V2 identity hash differs")
if state["current"] != identity.to_json():
    raise SystemExit("staged V2 current identity differs")
PY

printf 'Manifested Runtime V2 evolution 검증을 통과했습니다.\n'
