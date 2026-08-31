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
if [[ "$actual_revision" != "$git_head" \
  || "$actual_version" != "$git_head" \
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

python3 -B - "$runtime_archive" "$runtime_dir" <<'PY'
import shutil
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

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
actual_directories = set()
actual_files = {}
file_members = {}
seen_entries = set()

with tarfile.open(archive, "r") as bundle:
    for member in bundle.getmembers():
        member_path = PurePosixPath(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise SystemExit("runtime config contains an unsafe path")
        if not member_path.parts or member_path.parts[0] != "runtime":
            continue
        if len(member_path.parts) == 1:
            if not member.isdir():
                raise SystemExit("runtime config root is not a directory")
            continue

        relative = PurePosixPath(*member_path.parts[1:]).as_posix()
        if relative in seen_entries:
            raise SystemExit("runtime config contains a duplicate entry")
        seen_entries.add(relative)
        if member.issym() or member.islnk():
            raise SystemExit("runtime config contains a symlink")
        if member.isdir():
            actual_directories.add(relative)
        elif member.isfile():
            actual_files[relative] = stat.S_IMODE(member.mode)
            file_members[relative] = member
        else:
            raise SystemExit("runtime config contains a non-regular entry")

    if actual_directories != expected_directories:
        raise SystemExit("runtime config directory allowlist differs")
    if actual_files != expected_files:
        raise SystemExit("runtime config file allowlist or mode differs")

    root.mkdir(mode=0o700)
    for relative in sorted(expected_directories, key=lambda value: value.count("/")):
        (root / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
    for relative, expected_mode in expected_files.items():
        source = bundle.extractfile(file_members[relative])
        if source is None:
            raise SystemExit("runtime config file content is unavailable")
        target = root / relative
        with source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        target.chmod(expected_mode)

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
  "$runtime_dir/scripts/backup-production.sh" \
  "$runtime_dir/scripts/bootstrap-production.sh" \
  "$runtime_dir/scripts/backup_tools/backup_core.sh" \
  "$runtime_dir/scripts/deploy-production.sh" \
  "$runtime_dir/scripts/monitor-production.sh" \
  "$runtime_dir/scripts/production-status.sh"
(
  cd "$runtime_dir"
  python3 -B -m scripts.release_tools.release_contract --help >/dev/null
  python3 -B -m scripts.host_tools.production_host --help >/dev/null
  SSH_ORIGINAL_COMMAND=invalid python3 -B -m scripts.host_tools.production_fresh_bootstrap </dev/null >/dev/null 2>&1 || true
  python3 -B -m scripts.status_tools.production_status --help >/dev/null
  python3 -B -m scripts.status_tools.monitor_worker --help >/dev/null
)

docker compose \
  --project-directory "$runtime_dir" \
  --env-file "$ROOT_DIR/.env.production.example" \
  --file "$runtime_dir/compose.yaml" \
  config --quiet

printf 'Release/Deploy source 검증을 통과했습니다.\n'
