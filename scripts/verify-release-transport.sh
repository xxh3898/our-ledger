#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
git_head="$(git -C "$ROOT_DIR" rev-parse HEAD)"
if [[ ! "$git_head" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Release source HEAD가 exact commit SHA가 아닙니다.\n' >&2
  exit 1
fi
cd "$ROOT_DIR"

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  scripts/release_tools/test_release_contract.py
bash -n "$ROOT_DIR/scripts/detect-runtime-config-change.sh"

if ! command -v docker >/dev/null 2>&1 \
  || ! docker info >/dev/null 2>&1 \
  || ! docker compose version >/dev/null 2>&1; then
  printf 'Runtime config source gate에 Docker가 필요합니다.\n' >&2
  exit 1
fi

cleanup_task="${GITHUB_HEAD_REF:-}"
if [[ -z "$cleanup_task" ]]; then
  cleanup_task="$(git -C "$ROOT_DIR" branch --show-current)"
fi
if [[ -z "$cleanup_task" ]]; then
  cleanup_task="release-transport-${git_head:0:12}"
fi
if [[ ! "$cleanup_task" =~ ^[A-Za-z0-9._/-]{1,128}$ ]]; then
  printf 'Release source gate cleanup task 식별자가 유효하지 않습니다.\n' >&2
  exit 1
fi

image_tag="our-ledger-runtime-config:release-transport-${git_head:0:12}-$$"
container_name="our-ledger-runtime-config-release-transport-$$"

if docker container inspect "$container_name" >/dev/null 2>&1 \
  || docker image inspect "$image_tag" >/dev/null 2>&1; then
  printf 'Release source gate Docker resource 이름이 이미 사용 중입니다.\n' >&2
  exit 1
fi
runtime_parent="$(mktemp -d)"
runtime_parent="$(cd "$runtime_parent" && pwd -P)"
runtime_dir="$runtime_parent/runtime"
runtime_archive="$runtime_parent/runtime.tar"
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
  rm -rf -- "$runtime_parent"
  if docker container inspect "$container_name" >/dev/null 2>&1 \
    || docker image inspect "$image_tag" >/dev/null 2>&1; then
    printf 'Release source gate Docker residue가 남았습니다.\n' >&2
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
actual_project="$(
  docker image inspect \
    --format '{{ index .Config.Labels "io.chochiho.runtime-config.project" }}' \
    "$image_tag"
)"
actual_architecture="$(docker image inspect --format '{{.Architecture}}' "$image_tag")"
actual_source="$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.source" }}' \
    "$image_tag"
)"
if [[ "$actual_architecture" != arm64 \
  || "$actual_revision" != "$git_head" \
  || "$actual_version" != "$git_head" \
  || "$actual_source" != https://github.com/xxh3898/our-ledger \
  || "$actual_project" != our-ledger ]]; then
  printf 'Runtime config image identity label이 올바르지 않습니다.\n' >&2
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
  "$runtime_dir" <<'PY'
import sys
from pathlib import Path

from scripts.host_tools import host_state, production_deploy

archive = Path(sys.argv[1])
root = Path(sys.argv[2])
expected_directories = {
    "infra",
    "infra/nginx",
    "scripts",
    "scripts/backup_tools",
    "scripts/host_tools",
    "scripts/release_tools",
    "scripts/status_tools",
}
expected_files = {
    "compose.yaml": 0o600,
    "infra/nginx/nginx.conf": 0o600,
    "scripts/backup-our-ledger-bootstrap.sh": 0o700,
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
    "scripts/offsite-our-ledger-bootstrap.sh": 0o700,
    "scripts/production-status.sh": 0o700,
    "scripts/release_tools/release_contract.py": 0o700,
    "scripts/status_tools/monitor_policy.py": 0o600,
    "scripts/status_tools/monitor_worker.py": 0o600,
    "scripts/status_tools/production_status.py": 0o600,
}
manifest_bytes = Path("runtime-manifest.json").read_bytes()
manifest_profile = host_state.parse_runtime_manifest(manifest_bytes)
if manifest_profile.file_modes != expected_files:
    raise SystemExit("runtime config repository manifest payload differs")
if manifest_profile.directories != expected_directories:
    raise SystemExit("runtime config repository manifest directory set differs")

production_deploy._extract_verified_runtime(archive, root)
profile = host_state._validate_release(root)
if profile.format_version != 2:
    raise SystemExit("runtime config is not Manifested V2")
if profile.file_modes != expected_files:
    raise SystemExit("runtime config file allowlist or mode differs")
if profile.directories != expected_directories:
    raise SystemExit("runtime config directory allowlist differs")
if (root / host_state.RUNTIME_MANIFEST).read_bytes() != manifest_bytes:
    raise SystemExit("runtime config manifest bytes differ")
host_state.release_content_sha256(root)

for path in root.rglob("*"):
    lowered = path.name.lower()
    if lowered in {".env", "last-success.json", "monitor-state.json"}:
        raise SystemExit("runtime config contains a forbidden state or env file")
    if path.suffix.lower() in {".key", ".pem", ".p12", ".jks", ".dump"}:
        raise SystemExit("runtime config contains private or backup material")
    if path.is_file() and b"BEGIN PRIVATE KEY" in path.read_bytes():
        raise SystemExit("runtime config contains private key material")
PY

bash -n \
  "$runtime_dir/scripts/backup-our-ledger-bootstrap.sh" \
  "$runtime_dir/scripts/backup-production.sh" \
  "$runtime_dir/scripts/bootstrap-production.sh" \
  "$runtime_dir/scripts/backup_tools/backup_core.sh" \
  "$runtime_dir/scripts/deploy-production.sh" \
  "$runtime_dir/scripts/monitor-production.sh" \
  "$runtime_dir/scripts/offsite-backup-production.sh" \
  "$runtime_dir/scripts/offsite-our-ledger-bootstrap.sh" \
  "$runtime_dir/scripts/production-status.sh"
(
  cd "$runtime_dir"
  python3 -B -m scripts.release_tools.release_contract --help >/dev/null
  python3 -B -m scripts.host_tools.production_host --help >/dev/null
  SSH_ORIGINAL_COMMAND=invalid python3 -B -m scripts.host_tools.production_fresh_bootstrap </dev/null >/dev/null 2>&1 || true
  python3 -B -m scripts.backup_tools.offsite_backup --help >/dev/null
  python3 -B -m scripts.status_tools.production_status --help >/dev/null
  python3 -B -m scripts.status_tools.monitor_worker --help >/dev/null
)

docker compose \
  --project-directory "$runtime_dir" \
  --env-file "$ROOT_DIR/.env.production.example" \
  --file "$runtime_dir/compose.yaml" \
  config --quiet

printf 'Release/Deploy source 검증을 통과했습니다.\n'
