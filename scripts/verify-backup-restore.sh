#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"
ARTIFACT_HELPER="$ROOT_DIR/scripts/backup_tools/backup_artifact.py"
FIXTURE_SQL="$ROOT_DIR/scripts/backup_tools/fixture.sql"
STATE_SQL="$ROOT_DIR/scripts/backup_tools/state-fingerprint.sql"
INTEGRITY_SQL="$ROOT_DIR/scripts/backup_tools/integrity-check.sql"
STATE_CHECKER="$ROOT_DIR/scripts/backup_tools/check_fixture_state.py"
POSTGRES_IMAGE="postgres:18.6-alpine3.23@sha256:697c180dbf244d3ce4a8f4cbc0156cde840af055c1bf8b76aebe422a4822086f"
git_head="$(git rev-parse HEAD)"
[[ "$git_head" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'Backup/Restore source HEAD가 exact commit SHA가 아닙니다.\n' >&2
  exit 1
}

fail() {
  echo "$1" >&2
  exit 1
}

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  fail "Docker Compose를 사용할 수 없습니다."
fi
command -v python3 >/dev/null 2>&1 || fail "Python 3를 사용할 수 없습니다."

runtime_temp_root="${TMPDIR:-/tmp}"
runtime_temp_dir="$(mktemp -d "$runtime_temp_root/our-ledger-backup-restore.XXXXXX")"
runtime_temp_dir="$(cd "$runtime_temp_dir" && pwd -P)"
chmod 700 "$runtime_temp_dir"
synthetic_app_root="$runtime_temp_dir/host"
runtime_source="$runtime_temp_dir/runtime-source"
runtime_digest="sha256:$(printf 'd%.0s' {1..64})"
runtime_release="$synthetic_app_root/runtime-config/releases/${runtime_digest#sha256:}"

case "$runtime_temp_dir" in
  */our-ledger-backup-restore.*) ;;
  *) fail "backup/restore 검증 임시 directory 경계가 올바르지 않습니다." ;;
esac

run_token="$(date +%s)-$$"
source_project="our-ledger-backup-source-$run_token"
target_project="our-ledger-backup-target-$run_token"
failure_project="our-ledger-backup-failure-$run_token"
api_image="our-ledger-api:backup-$run_token"
unused_web_image="our-ledger-web:unused-$run_token"
runtime_password="synthetic-backup-$run_token"
env_file="$runtime_temp_dir/production.env"
backup_dir="$runtime_temp_dir/backups"
failure_backup_dir="$runtime_temp_dir/failure-backups"
fault_bin_dir="$runtime_temp_dir/fault-bin"
fault_python_dir="$runtime_temp_dir/fault-python"
cleanup_complete=false

mkdir -m 700 \
  "$backup_dir" \
  "$failure_backup_dir" \
  "$fault_bin_dir" \
  "$fault_python_dir"

python3 -B - "$ROOT_DIR" "$runtime_source" "$git_head" <<'PY'
import shutil
import sys
from pathlib import Path

repo = Path(sys.argv[1])
source = Path(sys.argv[2])
git_head = sys.argv[3]
sys.path.insert(0, str(repo))

from scripts.host_tools.host_state import RELEASE_DIRECTORIES, RELEASE_FILES

source.mkdir(mode=0o700)
for relative in sorted(RELEASE_DIRECTORIES, key=lambda item: item.count("/")):
    (source / relative).mkdir(mode=0o700)

labels = {
    "io.homeserver.cleanup.environment": "development",
    "io.homeserver.cleanup.project": "our-ledger",
    "io.homeserver.cleanup.task": "issue-41-host-state-runtime-config-staging",
    "io.homeserver.cleanup.lifecycle": "task",
    "io.homeserver.cleanup.retain": "false",
    "io.homeserver.cleanup.git-head": git_head,
}
targets = {
    "services": {"web", "api", "api-migration", "api-bootstrap", "postgres"},
    "networks": {"application", "database"},
    "volumes": {"postgres-data"},
}

def labeled_compose(value: str) -> str:
    output = []
    section = None
    for line in value.splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            section = line[:-1]
        output.append(line)
        if (
            section in targets
            and line.startswith("  ")
            and not line.startswith("    ")
            and line.endswith(":")
        ):
            name = line.strip()[:-1]
            if name in targets[section]:
                output.append("    labels:")
                for key, label_value in labels.items():
                    output.append(f'      {key}: "{label_value}"')
    return "\n".join(output) + "\n"

for relative, mode in RELEASE_FILES.items():
    target = source / relative
    repository_relative = "compose.prod.yaml" if relative == "compose.yaml" else relative
    repository_source = repo / repository_relative
    if relative == "compose.yaml":
        target.write_text(
            labeled_compose(repository_source.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    else:
        shutil.copyfile(repository_source, target)
    target.chmod(mode)
PY

python3 -B -m scripts.host_tools.synthetic_host \
  --app-root "$synthetic_app_root" \
  activate \
  --source-root "$runtime_source" \
  --application-revision "$git_head" \
  --runtime-config-digest "$runtime_digest" \
  --runtime-config-revision "$git_head"

COMPOSE_FILE="$runtime_release/compose.yaml"
BACKUP_COMMAND=(
  python3 -B -m scripts.host_tools.synthetic_host
  --app-root "$synthetic_app_root"
  backup
)
cleanup_labels=(
  --label io.homeserver.cleanup.environment=development
  --label io.homeserver.cleanup.project=our-ledger
  --label io.homeserver.cleanup.task=issue-41-host-state-runtime-config-staging
  --label io.homeserver.cleanup.lifecycle=task
  --label io.homeserver.cleanup.retain=false
  --label "io.homeserver.cleanup.git-head=$git_head"
)
{
  printf 'OUR_LEDGER_WEB_IMAGE=%s\n' "$unused_web_image"
  printf 'OUR_LEDGER_API_IMAGE=%s\n' "$api_image"
  printf 'OUR_LEDGER_ORIGIN_PORT=0\n'
  printf 'POSTGRES_DB=our_ledger_backup_fixture\n'
  printf 'POSTGRES_USER=our_ledger_backup_fixture\n'
  printf 'POSTGRES_PASSWORD=%s\n' "$runtime_password"
  printf 'CLOUDFLARE_ACCESS_ISSUER=https://backup.cloudflareaccess.example\n'
  printf 'CLOUDFLARE_ACCESS_JWK_SET_URI=https://backup.cloudflareaccess.example/cdn-cgi/access/certs\n'
  printf 'CLOUDFLARE_ACCESS_AUDIENCE=synthetic-backup-audience\n'
} > "$env_file"
chmod 600 "$env_file"

source_compose=(
  docker compose
  --project-name "$source_project"
  --env-file "$env_file"
  --file "$COMPOSE_FILE"
)
target_compose=(
  docker compose
  --project-name "$target_project"
  --env-file "$env_file"
  --file "$COMPOSE_FILE"
)
failure_compose=(
  docker compose
  --project-name "$failure_project"
  --env-file "$env_file"
  --file "$COMPOSE_FILE"
)

"${source_compose[@]}" config --format json \
  | python3 -B -c '
import json
import sys

git_head = sys.argv[1]
config = json.load(sys.stdin)
expected = {
    "io.homeserver.cleanup.environment": "development",
    "io.homeserver.cleanup.project": "our-ledger",
    "io.homeserver.cleanup.task": "issue-41-host-state-runtime-config-staging",
    "io.homeserver.cleanup.lifecycle": "task",
    "io.homeserver.cleanup.retain": "false",
    "io.homeserver.cleanup.git-head": git_head,
}
for group in ("services", "networks", "volumes"):
    for resource in config[group].values():
        if resource.get("labels") != expected:
            raise SystemExit("synthetic cleanup labels differ")
' "$git_head"

run_candidate_migration() {
  local project_kind="$1"
  local log_path="$2"
  case "$project_kind" in
    source)
      "${source_compose[@]}" run --rm --no-deps api-migration > "$log_path" 2>&1
      ;;
    target)
      "${target_compose[@]}" run --rm --no-deps api-migration > "$log_path" 2>&1
      ;;
    *)
      fail "알 수 없는 candidate migration 검증 project입니다."
      ;;
  esac
  if [[ "$(grep -Fxc 'migration-validation: success' "$log_path")" != "1" ]]; then
    fail "candidate migration success marker가 정확히 한 번 기록되지 않았습니다."
  fi
  if grep -Fq -- "$runtime_password" "$log_path"; then
    fail "candidate migration log에 synthetic credential이 노출됐습니다."
  fi
  if grep -Fq 'jdbc:postgresql://' "$log_path"; then
    fail "candidate migration success output에 connection URL이 노출됐습니다."
  fi
}

resource_residue() {
  local project_name="$1"
  local container_residue
  local network_residue
  local volume_residue

  container_residue="$(docker ps --all --quiet \
    --filter "label=com.docker.compose.project=$project_name")"
  network_residue="$(docker network ls --quiet \
    --filter "label=com.docker.compose.project=$project_name")"
  volume_residue="$(docker volume ls --quiet \
    --filter "label=com.docker.compose.project=$project_name")"
  [[ -z "$container_residue" && -z "$network_residue" && -z "$volume_residue" ]]
}

cleanup_resources() {
  local cleanup_status=0

  set +e
  "${source_compose[@]}" down --volumes --remove-orphans --timeout 45 >/dev/null 2>&1 \
    || cleanup_status=1
  "${target_compose[@]}" down --volumes --remove-orphans --timeout 45 >/dev/null 2>&1 \
    || cleanup_status=1
  "${failure_compose[@]}" down --volumes --remove-orphans --timeout 45 >/dev/null 2>&1 \
    || cleanup_status=1
  docker image rm "$api_image" >/dev/null 2>&1 || true

  resource_residue "$source_project" || cleanup_status=1
  resource_residue "$target_project" || cleanup_status=1
  resource_residue "$failure_project" || cleanup_status=1
  if docker image inspect "$api_image" >/dev/null 2>&1; then
    cleanup_status=1
  fi

  rm -rf -- "$runtime_temp_dir"
  cleanup_complete=true
  set -e
  return "$cleanup_status"
}

cleanup() {
  local original_status=$?
  local cleanup_status=0

  trap - EXIT HUP INT TERM
  if [[ "$cleanup_complete" != true ]]; then
    cleanup_resources || cleanup_status=1
  fi
  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

expect_failure() {
  local label="$1"
  shift
  if "$@" >"$runtime_temp_dir/expected-failure.stdout" \
    2>"$runtime_temp_dir/expected-failure.stderr"; then
    fail "$label failure path가 성공으로 처리됐습니다."
  fi
}

bundle_count() {
  find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name '*.backup' \
    | wc -l | tr -d '[:space:]'
}

file_sha256() {
  python3 -c '
import hashlib
import pathlib
import sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
' "$1"
}

assert_failed_backup_preserved_state() {
  [[ "$(file_sha256 "$marker_path")" == "$marker_sha_before" ]] \
    || fail "failed backup이 이전 last-success marker를 변경했습니다."
  [[ "$(bundle_count)" == "$bundle_count_before" ]] \
    || fail "failed backup이 final bundle 수를 변경했습니다."
  if find "$backup_dir" -mindepth 1 -maxdepth 1 -name '*.partial' -print -quit \
    | grep -q .; then
    fail "failed backup 뒤 partial artifact가 남았습니다."
  fi
}

compose_fingerprint() {
  local project_kind="$1"
  if [[ "$project_kind" == "source" ]]; then
    "${source_compose[@]}" exec -T postgres sh -ceu '
      exec psql -X \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB" \
        --tuples-only \
        --no-align \
        --set ON_ERROR_STOP=1
    ' < "$STATE_SQL"
  else
    "${target_compose[@]}" exec -T postgres sh -ceu '
      exec psql -X \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB" \
        --tuples-only \
        --no-align \
        --set ON_ERROR_STOP=1
    ' < "$STATE_SQL"
  fi
}

printf '\n[backup/restore 1/11] artifact/path failure contracts\n'
PYTHONDONTWRITEBYTECODE=1 python3 \
  "$ROOT_DIR/scripts/backup_tools/test_backup_artifact.py"

expect_failure "missing env file" \
  "${BACKUP_COMMAND[@]}" \
    --project-name missing-project \
    --env-file "$runtime_temp_dir/missing.env" \
    --backup-dir "$failure_backup_dir"
expect_failure "missing backup directory" \
  "${BACKUP_COMMAND[@]}" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir "$runtime_temp_dir/missing-backups"
expect_failure "repository backup directory" \
  "${BACKUP_COMMAND[@]}" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir "$ROOT_DIR"
expect_failure "root backup directory" \
  "${BACKUP_COMMAND[@]}" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir /

chmod 500 "$failure_backup_dir"
expect_failure "unwritable backup directory" \
  "${BACKUP_COMMAND[@]}" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir "$failure_backup_dir"
chmod 700 "$failure_backup_dir"

expect_failure "missing Compose project/postgres service" \
  "${BACKUP_COMMAND[@]}" \
    --project-name "our-ledger-backup-missing-$run_token" \
    --env-file "$env_file" \
    --backup-dir "$failure_backup_dir"

printf '\n[backup/restore 2/11] exact-HEAD API image, source migration and startup\n'
docker build \
  --progress plain \
  --no-cache \
  --pull \
  "${cleanup_labels[@]}" \
  --tag "$api_image" \
  --file "$ROOT_DIR/infra/docker/api.Dockerfile" \
  "$ROOT_DIR"

docker image inspect "$api_image" \
  | python3 -B -c '
import json
import sys

labels = json.load(sys.stdin)[0]["Config"]["Labels"]
expected = {
    "io.homeserver.cleanup.environment": "development",
    "io.homeserver.cleanup.project": "our-ledger",
    "io.homeserver.cleanup.task": "issue-41-host-state-runtime-config-staging",
    "io.homeserver.cleanup.lifecycle": "task",
    "io.homeserver.cleanup.retain": "false",
    "io.homeserver.cleanup.git-head": sys.argv[1],
}
if any(labels.get(key) != value for key, value in expected.items()):
    raise SystemExit("synthetic API image cleanup labels differ")
' "$git_head"

"${source_compose[@]}" up --detach --wait --wait-timeout 120 postgres
run_candidate_migration source "$runtime_temp_dir/source-migration.log"
"${source_compose[@]}" up --detach --wait --wait-timeout 240 api
source_postgres_id="$("${source_compose[@]}" ps --quiet postgres)"
source_api_id="$("${source_compose[@]}" ps --quiet api)"
[[ -n "$source_postgres_id" && -n "$source_api_id" ]] \
  || fail "source postgres/API container를 확인할 수 없습니다."
docker inspect "$source_postgres_id" \
  | python3 "$ARTIFACT_HELPER" check-container \
      --project-name "$source_project" \
      --compose-file "$COMPOSE_FILE" \
      --expected-image "$POSTGRES_IMAGE"

printf '\n[backup/restore 3/11] non-empty financial fixture and source fingerprint\n'
"${source_compose[@]}" exec -T postgres sh -ceu '
  exec psql -X \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1
' < "$FIXTURE_SQL"
source_state="$(compose_fingerprint source)"
printf '%s' "$source_state" | python3 "$STATE_CHECKER"
"${source_compose[@]}" exec -T postgres sh -ceu '
  exec psql -X \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1
' < "$INTEGRITY_SQL"

printf '\n[backup/restore 4/11] production-safe one-shot custom backup\n'
source_api_started_at="$(docker inspect --format '{{.State.StartedAt}}' "$source_api_id")"
"${BACKUP_COMMAND[@]}" \
  --project-name "$source_project" \
  --env-file "$env_file" \
  --backup-dir "$backup_dir" \
  > "$runtime_temp_dir/backup-success.log"

source_api_id_after="$("${source_compose[@]}" ps --quiet api)"
source_api_started_after="$(docker inspect --format '{{.State.StartedAt}}' "$source_api_id_after")"
[[ "$source_api_id_after" == "$source_api_id" \
  && "$source_api_started_after" == "$source_api_started_at" ]] \
  || fail "one-shot backup이 source API를 restart/recreate했습니다."
[[ "$(bundle_count)" == "1" ]] || fail "successful backup bundle이 정확히 하나가 아닙니다."

marker_path="$backup_dir/last-success.json"
bundle_name="$(python3 -c '
import json
import pathlib
import sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["bundleDirectory"])
' "$marker_path")"
dump_filename="$(python3 -c '
import json
import pathlib
import sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["dumpFilename"])
' "$marker_path")"
bundle_path="$backup_dir/$bundle_name"
dump_path="$bundle_path/$dump_filename"

python3 "$ARTIFACT_HELPER" verify --bundle-dir "$bundle_path" >/dev/null
"${source_compose[@]}" exec -T postgres sh -ceu '
  exec pg_restore --list
' < "$dump_path" >/dev/null
python3 "$ARTIFACT_HELPER" inventory --backup-dir "$backup_dir" \
  > "$runtime_temp_dir/inventory.json"
python3 -c '
import json
import pathlib
import sys
inventory = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert inventory["lastSuccessValid"] is True
assert len(inventory["valid"]) == 1
assert inventory["valid"][0]["isLatest"] is True
assert inventory["invalid"] == []
assert inventory["incomplete"] == []
assert inventory["foreign"] == []
' "$runtime_temp_dir/inventory.json"

printf '\n[backup/restore 5/11] marker preservation and injected backup failures\n'
marker_sha_before="$(file_sha256 "$marker_path")"
bundle_count_before="$(bundle_count)"

mkdir -m 700 "$synthetic_app_root/operations/lock"
expect_failure "concurrent project operation lock" \
  "${BACKUP_COMMAND[@]}" \
    --project-name "$source_project" \
    --env-file "$env_file" \
    --backup-dir "$backup_dir"
rmdir "$synthetic_app_root/operations/lock"

real_docker="$(command -v docker)"
fault_docker="$fault_bin_dir/docker"
{
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' 'set -euo pipefail'
  printf '%s\n' 'fault_mode="${OUR_LEDGER_FAULT_MODE:-}"'
  printf '%s\n' 'for argument in "$@"; do'
  printf '%s\n' '  case "$argument" in'
  printf '%s\n' '    *"exec pg_dump"*"--format=custom"*)'
  printf '%s\n' '      [[ "$fault_mode" == "pg-dump" ]] && exit 73'
  printf '%s\n' '      ;;'
  printf '%s\n' '    *"COUNT(*) FILTER (WHERE NOT success)"*"flyway_schema_history"*)'
  printf '%s\n' '      case "$fault_mode" in'
  printf '%s\n' '        schema-version-change|post-failed-migration)'
  printf '%s\n' '          if [[ ! -e "$OUR_LEDGER_FAULT_STATE_FILE" ]]; then'
  printf '%s\n' '            printf "%s\n" pre > "$OUR_LEDGER_FAULT_STATE_FILE"'
  printf '%s\n' '            exec "$OUR_LEDGER_REAL_DOCKER" "$@"'
  printf '%s\n' '          fi'
  printf '%s\n' '          if [[ "$fault_mode" == "schema-version-change" ]]; then'
  printf '%s\n' '            printf "%s\n" "0|9"'
  printf '%s\n' '          else'
  printf '%s\n' '            printf "%s\n" "1|8"'
  printf '%s\n' '          fi'
  printf '%s\n' '          exit 0'
  printf '%s\n' '          ;;'
  printf '%s\n' '      esac'
  printf '%s\n' '      ;;'
  printf '%s\n' '  esac'
  printf '%s\n' 'done'
  printf '%s\n' 'exec "$OUR_LEDGER_REAL_DOCKER" "$@"'
} > "$fault_docker"
chmod 700 "$fault_docker"

{
  printf '%s\n' 'import os'
  printf '%s\n' 'import sys'
  printf '%s\n' 'if os.environ.get("OUR_LEDGER_FAULT_MODE") == "dump-fsync" and "fsync-dump" in sys.argv:'
  printf '%s\n' '    def fail_fsync(_descriptor):'
  printf '%s\n' '        raise OSError("synthetic dump fsync failure")'
  printf '%s\n' '    os.fsync = fail_fsync'
} > "$fault_python_dir/sitecustomize.py"
chmod 600 "$fault_python_dir/sitecustomize.py"

expect_failure "pg_dump command" \
  env \
    PATH="$fault_bin_dir:$PATH" \
    OUR_LEDGER_REAL_DOCKER="$real_docker" \
    OUR_LEDGER_FAULT_MODE=pg-dump \
    "${BACKUP_COMMAND[@]}" \
      --project-name "$source_project" \
      --env-file "$env_file" \
      --backup-dir "$backup_dir"

assert_failed_backup_preserved_state

expect_failure "dump fsync" \
  env \
    PYTHONPATH="$fault_python_dir" \
    OUR_LEDGER_FAULT_MODE=dump-fsync \
    "${BACKUP_COMMAND[@]}" \
      --project-name "$source_project" \
      --env-file "$env_file" \
      --backup-dir "$backup_dir"
assert_failed_backup_preserved_state

expect_failure "Flyway schema version overlap" \
  env \
    PATH="$fault_bin_dir:$PATH" \
    OUR_LEDGER_REAL_DOCKER="$real_docker" \
    OUR_LEDGER_FAULT_MODE=schema-version-change \
    OUR_LEDGER_FAULT_STATE_FILE="$runtime_temp_dir/schema-version-state" \
    "${BACKUP_COMMAND[@]}" \
      --project-name "$source_project" \
      --env-file "$env_file" \
      --backup-dir "$backup_dir"
assert_failed_backup_preserved_state

expect_failure "post-check failed Flyway migration" \
  env \
    PATH="$fault_bin_dir:$PATH" \
    OUR_LEDGER_REAL_DOCKER="$real_docker" \
    OUR_LEDGER_FAULT_MODE=post-failed-migration \
    OUR_LEDGER_FAULT_STATE_FILE="$runtime_temp_dir/post-failed-state" \
    "${BACKUP_COMMAND[@]}" \
      --project-name "$source_project" \
      --env-file "$env_file" \
      --backup-dir "$backup_dir"
assert_failed_backup_preserved_state

printf '\n[backup/restore 6/11] corrupt/checksum/metadata rejection\n'
corruption_root="$runtime_temp_dir/corruption"
mkdir -m 700 "$corruption_root"
for label in zero truncated checksum metadata archive; do
  mkdir -m 700 "$corruption_root/$label"
  cp -R "$bundle_path" "$corruption_root/$label/"
done

zero_bundle="$corruption_root/zero/$bundle_name"
truncated_bundle="$corruption_root/truncated/$bundle_name"
checksum_bundle="$corruption_root/checksum/$bundle_name"
metadata_bundle="$corruption_root/metadata/$bundle_name"
archive_bundle="$corruption_root/archive/$bundle_name"

python3 - "$zero_bundle/$dump_filename" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b"")
PY
expect_failure "zero dump" \
  python3 "$ARTIFACT_HELPER" verify --bundle-dir "$zero_bundle"

python3 - "$truncated_bundle/$dump_filename" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b"PG")
PY
expect_failure "truncated dump" \
  python3 "$ARTIFACT_HELPER" verify --bundle-dir "$truncated_bundle"

checksum_file="$checksum_bundle/${dump_filename%.dump}.sha256"
printf '%064d  %s\n' 0 "$dump_filename" > "$checksum_file"
chmod 600 "$checksum_file"
expect_failure "checksum mismatch" \
  python3 "$ARTIFACT_HELPER" verify --bundle-dir "$checksum_bundle"

metadata_file="$metadata_bundle/${dump_filename%.dump}.json"
python3 - "$metadata_file" <<'PY'
import json
from pathlib import Path
import sys
path = Path(sys.argv[1])
metadata = json.loads(path.read_text())
metadata["schemaVersion"] = "7"
path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
path.chmod(0o600)
PY
expect_failure "metadata mismatch" \
  python3 "$ARTIFACT_HELPER" verify --bundle-dir "$metadata_bundle"

archive_dump="$archive_bundle/$dump_filename"
archive_metadata="$archive_bundle/${dump_filename%.dump}.json"
archive_checksum="$archive_bundle/${dump_filename%.dump}.sha256"
python3 - "$archive_dump" "$archive_metadata" "$archive_checksum" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

dump = Path(sys.argv[1])
metadata_path = Path(sys.argv[2])
checksum_path = Path(sys.argv[3])
content = dump.read_bytes()
truncated = content[:max(6, len(content) // 4)]
dump.write_bytes(truncated)
digest = hashlib.sha256(truncated).hexdigest()
metadata = json.loads(metadata_path.read_text())
metadata["sizeBytes"] = len(truncated)
metadata["sha256"] = digest
metadata_path.write_text(
    json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
)
checksum_path.write_text(f"{digest}  {dump.name}\n")
for path in (dump, metadata_path, checksum_path):
    path.chmod(0o600)
PY
python3 "$ARTIFACT_HELPER" verify --bundle-dir "$archive_bundle" >/dev/null
if "${source_compose[@]}" exec -T postgres sh -ceu '
  exec pg_restore --list
' < "$archive_dump" >/dev/null 2>&1; then
  fail "checksum이 맞지만 손상된 custom archive가 pg_restore list를 통과했습니다."
fi

"${source_compose[@]}" stop --timeout 45 api postgres >/dev/null

printf '\n[backup/restore 7/11] isolated empty target restore\n'
"${target_compose[@]}" up --detach --wait --wait-timeout 120 postgres
target_postgres_id="$("${target_compose[@]}" ps --quiet postgres)"
[[ -n "$target_postgres_id" && "$target_postgres_id" != "$source_postgres_id" ]] \
  || fail "restore target postgres가 source와 분리되지 않았습니다."
docker inspect "$target_postgres_id" \
  | python3 "$ARTIFACT_HELPER" check-container \
      --project-name "$target_project" \
      --compose-file "$COMPOSE_FILE" \
      --expected-image "$POSTGRES_IMAGE"

python3 "$ARTIFACT_HELPER" verify --bundle-dir "$bundle_path" >/dev/null
"${target_compose[@]}" exec -T postgres sh -ceu '
  exec pg_restore \
    --exit-on-error \
    --single-transaction \
    --no-owner \
    --no-acl \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB"
' < "$dump_path"

printf '\n[backup/restore 8/11] restored data, financial state and constraints\n'
target_state="$(compose_fingerprint target)"
printf '%s' "$target_state" | python3 "$STATE_CHECKER"
[[ "$target_state" == "$source_state" ]] \
  || fail "source와 restored target state fingerprint가 다릅니다."
"${target_compose[@]}" exec -T postgres sh -ceu '
  exec psql -X \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1
' < "$INTEGRITY_SQL"

printf '\n[backup/restore 9/11] restored database migration and production API readiness\n'
target_state_before_migration="$(compose_fingerprint target)"
run_candidate_migration target "$runtime_temp_dir/target-migration.log"
target_state_after_migration="$(compose_fingerprint target)"
[[ "$target_state_after_migration" == "$target_state_before_migration" ]] \
  || fail "restored V8 database candidate migration이 Flyway/data state를 변경했습니다."
"${target_compose[@]}" up --detach --wait --wait-timeout 240 api
"${target_compose[@]}" exec -T api \
  java -cp /opt/healthcheck HttpHealthCheck \
    http://127.0.0.1:8080/actuator/health/readiness
target_state_after_api="$(compose_fingerprint target)"
[[ "$target_state_after_api" == "$target_state" ]] \
  || fail "production API startup 뒤 restored Flyway/data state가 변경됐습니다."

"${target_compose[@]}" stop --timeout 45 api postgres >/dev/null

printf '\n[backup/restore 10/11] restore-target and unhealthy-service failures\n'
"${failure_compose[@]}" up --detach --wait --wait-timeout 120 postgres
if "${failure_compose[@]}" exec -T postgres sh -ceu '
  exec pg_restore \
    --exit-on-error \
    --single-transaction \
    --no-owner \
    --no-acl \
    --username "$POSTGRES_USER" \
    --dbname missing_restore_target
' < "$dump_path" >/dev/null 2>&1; then
  fail "존재하지 않는 restore target database가 성공으로 처리됐습니다."
fi

"${failure_compose[@]}" stop --timeout 30 postgres >/dev/null
expect_failure "stopped/unhealthy postgres" \
  "${BACKUP_COMMAND[@]}" \
    --project-name "$failure_project" \
    --env-file "$env_file" \
    --backup-dir "$failure_backup_dir"
[[ "$(file_sha256 "$marker_path")" == "$marker_sha_before" ]] \
  || fail "unhealthy service failure가 이전 source marker를 변경했습니다."

printf '\n[backup/restore 11/11] exact disposable resource cleanup\n'
if ! cleanup_resources; then
  fail "backup/restore 검증 resource residue cleanup에 실패했습니다."
fi

echo "Backup/Restore 검증을 통과했습니다."
