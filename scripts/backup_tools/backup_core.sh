#!/usr/bin/env bash
set -euo pipefail

umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
COMPOSE_FILE="$ROOT_DIR/compose.yaml"
ARTIFACT_HELPER="$ROOT_DIR/scripts/backup_tools/backup_artifact.py"
POSTGRES_IMAGE="postgres:18.6-alpine3.23@sha256:697c180dbf244d3ce4a8f4cbc0156cde840af055c1bf8b76aebe422a4822086f"

usage() {
  cat >&2 <<'EOF'
사용법:
  backup core \
    --project-name <production-compose-project> \
    --env-file <absolute-path-outside-repository> \
    --backup-dir <absolute-dedicated-owner-only-directory>
EOF
}

fail() {
  echo "$1" >&2
  exit 1
}

project_name=""
env_file=""
backup_dir=""

while (( $# > 0 )); do
  case "$1" in
    --project-name)
      [[ -z "$project_name" && $# -ge 2 ]] || { usage; exit 2; }
      project_name="$2"
      shift 2
      ;;
    --env-file)
      [[ -z "$env_file" && $# -ge 2 ]] || { usage; exit 2; }
      env_file="$2"
      shift 2
      ;;
    --backup-dir)
      [[ -z "$backup_dir" && $# -ge 2 ]] || { usage; exit 2; }
      backup_dir="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$project_name" && -n "$env_file" && -n "$backup_dir" ]] || {
  usage
  exit 2
}
[[ "$project_name" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]] \
  || fail "Compose project 이름이 안전한 형식이 아닙니다."

command -v python3 >/dev/null 2>&1 || fail "Python 3를 사용할 수 없습니다."
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  fail "Docker Compose를 사용할 수 없습니다."
fi

env_file="$(python3 "$ARTIFACT_HELPER" validate-env \
  --repo-root "$ROOT_DIR" \
  --path "$env_file")"
backup_dir="$(python3 "$ARTIFACT_HELPER" validate-backup-dir \
  --repo-root "$ROOT_DIR" \
  --path "$backup_dir")"

staging_dir=""

cleanup() {
  local original_status=$?
  local cleanup_status=0

  trap - EXIT HUP INT TERM
  set +e

  if [[ -n "$staging_dir" && -e "$staging_dir" ]]; then
    python3 "$ARTIFACT_HELPER" cleanup-staging \
      --backup-dir "$backup_dir" \
      --staging-dir "$staging_dir" >/dev/null 2>&1 \
      || cleanup_status=1
  fi
  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

compose=(
  docker compose
  --project-name "$project_name"
  --env-file "$env_file"
  --file "$COMPOSE_FILE"
)

if ! "${compose[@]}" config --quiet >/dev/null; then
  fail "production Compose/env 계약을 검증할 수 없습니다."
fi

postgres_ids="$("${compose[@]}" ps --all --quiet postgres)"
if [[ -z "$postgres_ids" || "$postgres_ids" == *$'\n'* ]]; then
  fail "지정한 Compose project의 postgres service container를 정확히 하나 확인해야 합니다."
fi
postgres_id="$postgres_ids"

if ! docker inspect "$postgres_id" \
  | python3 "$ARTIFACT_HELPER" check-container \
      --project-name "$project_name" \
      --compose-file "$COMPOSE_FILE" \
      --expected-image "$POSTGRES_IMAGE"; then
  fail "postgres runtime 경계 또는 health가 production backup 계약과 다릅니다."
fi

pg_dump_version="$("${compose[@]}" exec -T postgres sh -ceu 'pg_dump --version')"
case "$pg_dump_version" in
  "pg_dump (PostgreSQL) 18.6"*) ;;
  *) fail "pg_dump client가 PostgreSQL 18.6이 아닙니다." ;;
esac

postgres_server_version="$("${compose[@]}" exec -T postgres sh -ceu '
  exec psql -X \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SHOW server_version"
')"
case "$postgres_server_version" in
  18.6|18.6\ *) ;;
  *) fail "PostgreSQL server가 18.6이 아닙니다." ;;
esac

read_flyway_state() {
  "${compose[@]}" exec -T postgres sh -ceu '
  exec psql -X \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --field-separator "|" \
    --set ON_ERROR_STOP=1 \
    --command "
      SELECT
        COUNT(*) FILTER (WHERE NOT success),
        (SELECT version
           FROM flyway_schema_history
          WHERE success
          ORDER BY installed_rank DESC
          LIMIT 1)
        FROM flyway_schema_history
    "
'
}

flyway_state_pattern='^([0-9]+)[|]([1-9][0-9]*([.][0-9]+)*)$'
if ! pre_flyway_state="$(read_flyway_state)"; then
  fail "backup 전 Flyway state를 확인할 수 없습니다."
fi
[[ "$pre_flyway_state" =~ $flyway_state_pattern ]] \
  || fail "backup 전 Flyway state 형식이 잘못됐습니다."
pre_failed_migration_count="${BASH_REMATCH[1]}"
schema_version="${BASH_REMATCH[2]}"
[[ "$pre_failed_migration_count" == "0" ]] \
  || fail "실패한 Flyway migration이 있어 backup을 만들 수 없습니다."

created_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
stem="$(python3 "$ARTIFACT_HELPER" new-stem \
  --created-at "$created_at" \
  --schema-version "$schema_version")"
final_bundle_name="$stem.backup"
dump_filename="$stem.dump"
staging_dir="$backup_dir/.our-ledger_backup_$stem.partial"
final_bundle="$backup_dir/$final_bundle_name"

[[ ! -e "$final_bundle" && ! -L "$final_bundle" ]] \
  || fail "같은 final backup artifact가 이미 존재합니다."
if ! mkdir -m 700 "$staging_dir"; then
  fail "owner-only partial backup directory를 만들 수 없습니다."
fi
dump_path="$staging_dir/$dump_filename"

if ! "${compose[@]}" exec -T postgres sh -ceu '
  exec pg_dump \
    --format=custom \
    --compress=gzip:6 \
    --no-acl \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB"
' > "$dump_path"; then
  fail "pg_dump custom archive 생성에 실패했습니다."
fi
chmod 600 "$dump_path"

python3 "$ARTIFACT_HELPER" fsync-dump \
  --backup-dir "$backup_dir" \
  --staging-dir "$staging_dir" \
  --dump-filename "$dump_filename"

if ! "${compose[@]}" exec -T postgres sh -ceu '
  exec pg_restore --list
' < "$dump_path" >/dev/null; then
  fail "pg_restore가 partial custom archive 목록을 읽지 못했습니다."
fi

if ! post_flyway_state="$(read_flyway_state)"; then
  fail "backup 후 Flyway state를 확인할 수 없습니다."
fi
[[ "$post_flyway_state" =~ $flyway_state_pattern ]] \
  || fail "backup 후 Flyway state 형식이 잘못됐습니다."
post_failed_migration_count="${BASH_REMATCH[1]}"
post_schema_version="${BASH_REMATCH[2]}"
[[ "$post_failed_migration_count" == "0" ]] \
  || fail "backup window 중 실패한 Flyway migration이 감지됐습니다."
[[ "$post_schema_version" == "$schema_version" ]] \
  || fail "backup window 중 Flyway schema version 변경이 감지됐습니다."

python3 "$ARTIFACT_HELPER" write-sidecars \
  --backup-dir "$backup_dir" \
  --staging-dir "$staging_dir" \
  --dump-filename "$dump_filename" \
  --created-at "$created_at" \
  --schema-version "$schema_version" \
  --pg-dump-version "$pg_dump_version" \
  --postgres-server-version "$postgres_server_version"

python3 "$ARTIFACT_HELPER" verify \
  --bundle-dir "$staging_dir" \
  --allow-staging >/dev/null

final_dump="$(python3 "$ARTIFACT_HELPER" commit \
  --backup-dir "$backup_dir" \
  --staging-dir "$staging_dir" \
  --final-bundle-name "$final_bundle_name")"
staging_dir=""

printf '백업 완료: %s\n' "$final_dump"
printf 'createdAt: %s\n' "$created_at"
printf 'schemaVersion: %s\n' "$schema_version"
