#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1 \
  || ! docker info >/dev/null 2>&1 \
  || ! docker compose version >/dev/null 2>&1 \
  || ! command -v python3 >/dev/null 2>&1 \
  || ! command -v git >/dev/null 2>&1; then
  echo "Fresh-host bootstrap 검증에 Docker Compose, Python 3, Git이 필요합니다." >&2
  exit 1
fi

git_head="$(git rev-parse HEAD)"
if [[ ! "$git_head" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Fresh-host bootstrap 검증 HEAD가 exact SHA가 아닙니다." >&2
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  scripts.host_tools.test_fresh_host_bootstrap

run_token="$(date +%s)-$$"
project_name="our-ledger-fresh-$run_token"
runtime_parent="$(cd "${TMPDIR:-/tmp}" && pwd -P)"
runtime_root="$(mktemp -d "$runtime_parent/our-ledger-fresh.XXXXXX")"
host_root="$runtime_root/host"
backup_dir="$runtime_root/backups"
env_file="$runtime_root/.env"
input_file="$runtime_root/household-bootstrap.json"
context_dir="$runtime_root/runtime-context"
override_file="$runtime_root/compose.labels.yaml"
api_image="ghcr.io/xxh3898/our-ledger-api:$git_head"
web_image="ghcr.io/xxh3898/our-ledger-web:$git_head"
runtime_image="our-ledger-runtime-config:fresh-${git_head:0:12}-$run_token"
api_created=false
web_created=false
runtime_created=false

case "$runtime_root" in
  "$runtime_parent"/our-ledger-fresh.*) ;;
  *)
    echo "Fresh-host bootstrap 임시 경계가 올바르지 않습니다." >&2
    exit 1
    ;;
esac
chmod 700 "$runtime_root"
mkdir -m 700 "$backup_dir" "$context_dir"

loopback_port="$(python3 -B - <<'PY'
import socket

with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"

python3 -B - \
  "$env_file" \
  "$input_file" \
  "$override_file" \
  "$api_image" \
  "$web_image" \
  "$project_name" \
  "$loopback_port" \
  "$git_head" \
  "$run_token" <<'PY'
from pathlib import Path
import json
import sys

(
    env_path,
    input_path,
    override_path,
    api_image,
    web_image,
    project_name,
    port,
    revision,
    run_token,
) = sys.argv[1:]

Path(env_path).write_text(
    "\n".join(
        (
            f"POSTGRES_DB=our_ledger_fresh_{run_token.replace('-', '_')}",
            "POSTGRES_USER=our_ledger_fresh",
            f"POSTGRES_PASSWORD=synthetic-fresh-{run_token}",
            f"OUR_LEDGER_API_IMAGE={api_image}",
            f"OUR_LEDGER_WEB_IMAGE={web_image}",
            f"OUR_LEDGER_ORIGIN_PORT={port}",
            "CLOUDFLARE_ACCESS_ISSUER=https://fresh.invalid",
            "CLOUDFLARE_ACCESS_JWK_SET_URI=https://fresh.invalid/certs",
            "CLOUDFLARE_ACCESS_AUDIENCE=synthetic-fresh-audience",
            f"OUR_LEDGER_EXPECTED_COMPOSE_PROJECT={project_name}",
        )
    )
    + "\n",
    encoding="utf-8",
)
Path(env_path).chmod(0o600)
Path(input_path).write_text(
    json.dumps(
        {
            "formatVersion": 1,
            "householdName": "SyntheticFreshHousehold",
            "owner": {
                "email": "fresh-owner-53@example.test",
                "displayName": "SyntheticFreshOwner",
            },
            "member": {
                "email": "fresh-member-53@example.test",
                "displayName": "SyntheticFreshMember",
            },
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
Path(input_path).chmod(0o600)

labels = {
    "io.homeserver.cleanup.environment": "development",
    "io.homeserver.cleanup.project": "our-ledger",
    "io.homeserver.cleanup.task": "issue-53-fresh-host-bootstrap",
    "io.homeserver.cleanup.lifecycle": "task",
    "io.homeserver.cleanup.retain": "false",
    "io.homeserver.cleanup.git-head": revision,
}
lines = ["services:"]
for service in ("web", "api", "api-migration", "api-bootstrap", "postgres"):
    lines.extend((f"  {service}:", "    labels:"))
    lines.extend(f'      {key}: "{value}"' for key, value in labels.items())
for group, names in (
    ("networks", ("application", "database")),
    ("volumes", ("postgres-data",)),
):
    lines.append(f"{group}:")
    for name in names:
        lines.extend((f"  {name}:", "    labels:"))
        lines.extend(f'      {key}: "{value}"' for key, value in labels.items())
Path(override_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
Path(override_path).chmod(0o600)
PY

cleanup() {
  local original_status=$?
  local cleanup_status=0
  local release_dir="$host_root/runtime-config/releases/${runtime_digest#sha256:}"

  trap - EXIT HUP INT TERM
  set +e
  if [[ -f "$release_dir/compose.yaml" ]]; then
    docker compose \
      --project-name "$project_name" \
      --project-directory "$release_dir" \
      --env-file "$env_file" \
      --file "$release_dir/compose.yaml" \
      down --volumes --remove-orphans --timeout 45 >/dev/null 2>&1 \
      || cleanup_status=1
  fi
  [[ "$runtime_created" == false ]] || docker image rm --force "$runtime_image" >/dev/null 2>&1 || cleanup_status=1
  [[ "$web_created" == false ]] || docker image rm --force "$web_image" >/dev/null 2>&1 || cleanup_status=1
  [[ "$api_created" == false ]] || docker image rm --force "$api_image" >/dev/null 2>&1 || cleanup_status=1

  container_residue="$(docker ps --all --quiet --filter "label=com.docker.compose.project=$project_name")"
  network_residue="$(docker network ls --quiet --filter "label=com.docker.compose.project=$project_name")"
  volume_residue="$(docker volume ls --quiet --filter "label=com.docker.compose.project=$project_name")"
  if [[ -n "$container_residue" || -n "$network_residue" || -n "$volume_residue" ]]; then
    echo "Fresh-host bootstrap Docker residue가 남았습니다." >&2
    cleanup_status=1
  fi

  python3 -B - "$runtime_root" "$runtime_parent" <<'PY'
from pathlib import Path
import shutil
import sys

target = Path(sys.argv[1])
parent = Path(sys.argv[2])
if target.parent != parent or not target.name.startswith("our-ledger-fresh."):
    raise SystemExit("fresh-host bootstrap cleanup boundary differs")
shutil.rmtree(target)
PY

  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

runtime_digest="sha256:$(printf '0%.0s' {1..64})"
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

for image in "$api_image" "$web_image" "$runtime_image"; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "Fresh-host bootstrap 검증 image tag가 이미 사용 중입니다: $image" >&2
    exit 1
  fi
done

cleanup_labels=(
  --label io.homeserver.cleanup.environment=development
  --label io.homeserver.cleanup.project=our-ledger
  --label io.homeserver.cleanup.task=issue-53-fresh-host-bootstrap
  --label io.homeserver.cleanup.lifecycle=task
  --label io.homeserver.cleanup.retain=false
  --label "io.homeserver.cleanup.git-head=$git_head"
)
oci_labels=(
  --label org.opencontainers.image.source=https://github.com/xxh3898/our-ledger
  --label "org.opencontainers.image.revision=$git_head"
  --label "org.opencontainers.image.version=$git_head"
)

docker build \
  "${cleanup_labels[@]}" \
  "${oci_labels[@]}" \
  --tag "$api_image" \
  --file "$ROOT_DIR/infra/docker/api.Dockerfile" \
  "$ROOT_DIR"
api_created=true

docker build \
  "${cleanup_labels[@]}" \
  "${oci_labels[@]}" \
  --tag "$web_image" \
  --file "$ROOT_DIR/infra/docker/web.Dockerfile" \
  "$ROOT_DIR"
web_created=true

docker compose \
  --project-name "$project_name" \
  --env-file "$env_file" \
  --file "$ROOT_DIR/compose.prod.yaml" \
  --file "$override_file" \
  --profile migration \
  --profile bootstrap \
  config > "$context_dir/compose.prod.yaml"
chmod 600 "$context_dir/compose.prod.yaml"

python3 -B - "$ROOT_DIR" "$context_dir" <<'PY'
from pathlib import Path
import shutil
import sys

from scripts.host_tools import host_state

root = Path(sys.argv[1])
context = Path(sys.argv[2])
manifest_source = root / host_state.RUNTIME_MANIFEST
manifest_bytes = manifest_source.read_bytes()
profile = host_state.parse_runtime_manifest(manifest_bytes)
manifest_target = context / host_state.RUNTIME_MANIFEST
shutil.copyfile(manifest_source, manifest_target)
manifest_target.chmod(0o600)
for relative, mode in profile.files:
    if relative == "compose.yaml":
        continue
    target = context / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / relative, target)
    target.chmod(mode)
shutil.copyfile(root / "runtime-config.Dockerfile", context / "runtime-config.Dockerfile")
PY

docker build \
  --network none \
  --build-arg "REVISION=$git_head" \
  "${cleanup_labels[@]}" \
  --tag "$runtime_image" \
  --file "$context_dir/runtime-config.Dockerfile" \
  "$context_dir"
runtime_created=true
runtime_digest="$(docker image inspect --format '{{.Id}}' "$runtime_image")"
if [[ ! "$runtime_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Synthetic runtime-config digest가 invalid입니다." >&2
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 python3 - \
  "$host_root" \
  "$env_file" \
  "$input_file" \
  "$backup_dir" \
  "$project_name" \
  "$git_head" \
  "$api_image" \
  "$web_image" \
  "$runtime_image" \
  "$runtime_digest" \
  "$loopback_port" <<'PY'
from pathlib import Path
import os
import sys

from scripts.backup_tools import backup_artifact
from scripts.host_tools import fresh_bootstrap_state, host_state
from scripts.host_tools.fresh_host_bootstrap import (
    FreshBootstrapError,
    read_token,
    run_fresh_bootstrap,
)
from scripts.host_tools.synthetic_fresh_bootstrap import SyntheticFreshBootstrapAdapter

(
    host_root,
    env_file,
    input_file,
    backup_dir,
    project_name,
    revision,
    api_image,
    web_image,
    runtime_image,
    runtime_digest,
    loopback_port,
) = sys.argv[1:]
paths = host_state.HostPaths(Path(host_root))
host_state.initialize_layout(paths)
adapter = SyntheticFreshBootstrapAdapter(
    paths=paths,
    env_file=Path(env_file),
    input_file=Path(input_file),
    backup_directory=Path(backup_dir),
    project_name=project_name,
    revision=revision,
    api_image=api_image,
    web_image=web_image,
    runtime_image=runtime_image,
    runtime_digest=runtime_digest,
    loopback_port=int(loopback_port),
)
command = f"bootstrap-our-ledger-v1 {revision} {runtime_digest} synthetic_actor"
crashed = False

def crash_after_migration(phase: str) -> None:
    global crashed
    if phase == "MIGRATION_VERIFIED" and not crashed:
        crashed = True
        raise RuntimeError("synthetic crash")

try:
    run_fresh_bootstrap(
        command,
        read_token(b"synthetic-token\n"),
        paths=paths,
        adapter=adapter,
        clock=lambda: "2026-08-30T00:00:00Z",
        crash_hook=crash_after_migration,
    )
except FreshBootstrapError as error:
    reasons = []
    current = error
    while current is not None and len(reasons) < 4:
        reasons.append(str(current))
        current = current.__cause__
    if not paths.pending_file.exists():
        raise SystemExit("synthetic pre-pending failure: " + " <- ".join(reasons))
    with host_state.OperationLock(paths) as lock:
        interrupted = fresh_bootstrap_state.read(paths, lock, required=True)
    if interrupted["phase"] != "MIGRATION_VERIFIED":
        raise SystemExit(
            "synthetic migration execution failed: " + " <- ".join(reasons)
        )
else:
    raise SystemExit("synthetic migration crash did not interrupt transaction")

with host_state.OperationLock(paths) as lock:
    pending = fresh_bootstrap_state.read(paths, lock, required=True)
    if pending["phase"] != "MIGRATION_VERIFIED":
        raise SystemExit(
            f"synthetic migration recovery phase differs: {pending['phase']!r}"
        )
if os.path.lexists(paths.current) or os.path.lexists(paths.state_file):
    raise SystemExit("fresh bootstrap published before recovery")

result = run_fresh_bootstrap(
    command,
    read_token(b"synthetic-token\n"),
    paths=paths,
    adapter=adapter,
    clock=lambda: "2026-08-30T00:01:00Z",
)
if result.status != "SUCCESS":
    raise SystemExit("fresh bootstrap recovery did not succeed")
if os.path.lexists(input_file):
    raise SystemExit("one-time bootstrap input remains")
if not adapter.household_bootstrap_is_exact():
    raise SystemExit("fresh household state differs")
inventory = backup_artifact.inventory(Path(backup_dir))
if not inventory["lastSuccessValid"] or len(inventory["valid"]) != 1:
    raise SystemExit("first verified backup differs")
with host_state.OperationLock(paths) as lock:
    state = host_state.inspect_state(paths, lock)
if state["status"] != "READY" or state["pending"]:
    raise SystemExit("fresh committed host state differs")

before = adapter.read_schema_authority()
try:
    run_fresh_bootstrap(
        command,
        read_token(b"synthetic-token\n"),
        paths=paths,
        adapter=adapter,
        clock=lambda: "2026-08-30T00:02:00Z",
    )
except FreshBootstrapError:
    pass
else:
    raise SystemExit("committed fresh bootstrap rerun was accepted")
if adapter.read_schema_authority() != before or not adapter.household_bootstrap_is_exact():
    raise SystemExit("blocked rerun changed production data authority")
print("fresh-host-bootstrap: synthetic lifecycle success")
PY

if git diff --exit-code -- backend/src/main/resources/db/migration >/dev/null; then
  :
else
  echo "Fresh-host bootstrap 검증 중 V1~V8 migration이 변경됐습니다." >&2
  exit 1
fi

printf 'Fresh-host bootstrap 검증을 통과했습니다.\n'
