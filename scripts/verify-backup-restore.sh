#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
COMPOSE_FILE="$ROOT_DIR/compose.prod.yaml"
BACKUP_COMMAND="$ROOT_DIR/scripts/backup-production.sh"
ARTIFACT_HELPER="$ROOT_DIR/scripts/backup_tools/backup_artifact.py"
FIXTURE_SQL="$ROOT_DIR/scripts/backup_tools/fixture.sql"
STATE_SQL="$ROOT_DIR/scripts/backup_tools/state-fingerprint.sql"
INTEGRITY_SQL="$ROOT_DIR/scripts/backup_tools/integrity-check.sql"
STATE_CHECKER="$ROOT_DIR/scripts/backup_tools/check_fixture_state.py"
POSTGRES_IMAGE="postgres:18.6-alpine3.23@sha256:697c180dbf244d3ce4a8f4cbc0156cde840af055c1bf8b76aebe422a4822086f"

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
cleanup_complete=false

mkdir -m 700 "$backup_dir" "$failure_backup_dir" "$fault_bin_dir"
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
  "$BACKUP_COMMAND" \
    --project-name missing-project \
    --env-file "$runtime_temp_dir/missing.env" \
    --backup-dir "$failure_backup_dir"
expect_failure "missing backup directory" \
  "$BACKUP_COMMAND" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir "$runtime_temp_dir/missing-backups"
expect_failure "repository backup directory" \
  "$BACKUP_COMMAND" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir "$ROOT_DIR"
expect_failure "root backup directory" \
  "$BACKUP_COMMAND" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir /

chmod 500 "$failure_backup_dir"
expect_failure "unwritable backup directory" \
  "$BACKUP_COMMAND" \
    --project-name missing-project \
    --env-file "$env_file" \
    --backup-dir "$failure_backup_dir"
chmod 700 "$failure_backup_dir"

expect_failure "missing Compose project/postgres service" \
  "$BACKUP_COMMAND" \
    --project-name "our-ledger-backup-missing-$run_token" \
    --env-file "$env_file" \
    --backup-dir "$failure_backup_dir"

printf '\n[backup/restore 2/11] exact-HEAD API image and source startup\n'
docker build \
  --progress plain \
  --no-cache \
  --pull \
  --tag "$api_image" \
  --file "$ROOT_DIR/infra/docker/api.Dockerfile" \
  "$ROOT_DIR"

"${source_compose[@]}" up --detach --wait --wait-timeout 240 postgres api
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
"$BACKUP_COMMAND" \
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

mkdir -m 700 "$backup_dir/.our-ledger-backup.lock"
expect_failure "concurrent backup lock" \
  "$BACKUP_COMMAND" \
    --project-name "$source_project" \
    --env-file "$env_file" \
    --backup-dir "$backup_dir"
rmdir "$backup_dir/.our-ledger-backup.lock"

real_docker="$(command -v docker)"
fault_docker="$fault_bin_dir/docker"
{
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' 'set -euo pipefail'
  printf '%s\n' 'for argument in "$@"; do'
  printf '%s\n' '  case "$argument" in'
  printf '%s\n' '    *"exec pg_dump"*"--format=custom"*) exit 73 ;;'
  printf '%s\n' '  esac'
  printf '%s\n' 'done'
  printf '%s\n' 'exec "$OUR_LEDGER_REAL_DOCKER" "$@"'
} > "$fault_docker"
chmod 700 "$fault_docker"

expect_failure "pg_dump command" \
  env \
    PATH="$fault_bin_dir:$PATH" \
    OUR_LEDGER_REAL_DOCKER="$real_docker" \
    "$BACKUP_COMMAND" \
      --project-name "$source_project" \
      --env-file "$env_file" \
      --backup-dir "$backup_dir"

[[ "$(file_sha256 "$marker_path")" == "$marker_sha_before" ]] \
  || fail "failed backup이 이전 last-success marker를 변경했습니다."
[[ "$(bundle_count)" == "$bundle_count_before" ]] \
  || fail "failed backup이 final bundle 수를 변경했습니다."
if find "$backup_dir" -mindepth 1 -maxdepth 1 -name '*.partial' -print -quit \
  | grep -q .; then
  fail "failed backup 뒤 partial artifact가 남았습니다."
fi

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

printf '\n[backup/restore 9/11] restored database production API readiness\n'
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
  "$BACKUP_COMMAND" \
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
