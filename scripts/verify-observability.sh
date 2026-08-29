#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.prod.yaml"
BACKUP_HELPER="$ROOT_DIR/scripts/backup_tools/backup_artifact.py"

if ! command -v docker >/dev/null 2>&1 \
  || ! docker compose version >/dev/null 2>&1 \
  || ! command -v python3 >/dev/null 2>&1 \
  || ! command -v curl >/dev/null 2>&1; then
  echo "Observability 검증에 필요한 Docker Compose, Python, curl이 없습니다." >&2
  exit 1
fi

project_name="our-ledger-observability-$(date +%s)-$$"
api_image="our-ledger-api:$project_name"
web_image="our-ledger-web:$project_name"
temporary_root="${TMPDIR:-/tmp}"
status_root="$(mktemp -d "$temporary_root/our-ledger-observability.XXXXXX")"
env_file="$status_root/production.env"
backup_directory="$status_root/backups"
runtime_password="observability-only-$project_name"

case "$status_root" in
  "$temporary_root"/our-ledger-observability.*) ;;
  *)
    echo "Observability 임시 directory 경계가 올바르지 않습니다." >&2
    exit 1
    ;;
esac

chmod 700 "$status_root"
mkdir -m 700 "$backup_directory"

export OUR_LEDGER_WEB_IMAGE="$web_image"
export OUR_LEDGER_API_IMAGE="$api_image"
export OUR_LEDGER_ORIGIN_PORT=0
export POSTGRES_DB=our_ledger_observability
export POSTGRES_USER=our_ledger_observability
export POSTGRES_PASSWORD="$runtime_password"
export CLOUDFLARE_ACCESS_ISSUER=https://observability.cloudflareaccess.example
export CLOUDFLARE_ACCESS_JWK_SET_URI=https://observability.cloudflareaccess.example/certs
export CLOUDFLARE_ACCESS_AUDIENCE=observability-audience
export OUR_LEDGER_RECURRING_INITIAL_DELAY_MS=0
export OUR_LEDGER_RECURRING_POLL_DELAY_MS=10000

umask 077
{
  printf 'OUR_LEDGER_WEB_IMAGE=%s\n' "$OUR_LEDGER_WEB_IMAGE"
  printf 'OUR_LEDGER_API_IMAGE=%s\n' "$OUR_LEDGER_API_IMAGE"
  printf 'OUR_LEDGER_ORIGIN_PORT=%s\n' "$OUR_LEDGER_ORIGIN_PORT"
  printf 'POSTGRES_DB=%s\n' "$POSTGRES_DB"
  printf 'POSTGRES_USER=%s\n' "$POSTGRES_USER"
  printf 'POSTGRES_PASSWORD=%s\n' "$POSTGRES_PASSWORD"
  printf 'CLOUDFLARE_ACCESS_ISSUER=%s\n' "$CLOUDFLARE_ACCESS_ISSUER"
  printf 'CLOUDFLARE_ACCESS_JWK_SET_URI=%s\n' "$CLOUDFLARE_ACCESS_JWK_SET_URI"
  printf 'CLOUDFLARE_ACCESS_AUDIENCE=%s\n' "$CLOUDFLARE_ACCESS_AUDIENCE"
  printf 'OUR_LEDGER_RECURRING_INITIAL_DELAY_MS=%s\n' "$OUR_LEDGER_RECURRING_INITIAL_DELAY_MS"
  printf 'OUR_LEDGER_RECURRING_POLL_DELAY_MS=%s\n' "$OUR_LEDGER_RECURRING_POLL_DELAY_MS"
} > "$env_file"
chmod 600 "$env_file"

compose=(
  docker compose
  --project-name "$project_name"
  --env-file "$env_file"
  -f "$COMPOSE_FILE"
)

cleanup() {
  local original_status=$?
  local cleanup_status=0
  local container_residue=""
  local network_residue=""
  local volume_residue=""
  local image_residue=""

  trap - EXIT HUP INT TERM
  set +e
  "${compose[@]}" down --volumes --remove-orphans --timeout 45 >/dev/null 2>&1
  docker image rm "$api_image" "$web_image" >/dev/null 2>&1 || true

  container_residue="$(docker ps --all --quiet \
    --filter "label=com.docker.compose.project=$project_name")"
  network_residue="$(docker network ls --quiet \
    --filter "label=com.docker.compose.project=$project_name")"
  volume_residue="$(docker volume ls --quiet \
    --filter "label=com.docker.compose.project=$project_name")"
  if docker image inspect "$api_image" >/dev/null 2>&1 \
    || docker image inspect "$web_image" >/dev/null 2>&1; then
    image_residue="present"
  fi
  if [[ -n "$container_residue" || -n "$network_residue" \
    || -n "$volume_residue" || -n "$image_residue" ]]; then
    echo "고유 observability 검증 Docker resource가 남았습니다." >&2
    cleanup_status=1
  fi

  case "$status_root" in
    "$temporary_root"/our-ledger-observability.*)
      rm -rf -- "$status_root"
      ;;
    *)
      echo "Observability 임시 directory cleanup 경계가 바뀌었습니다." >&2
      cleanup_status=1
      ;;
  esac
  if [[ -e "$status_root" ]]; then
    echo "Observability 검증 임시 directory가 남았습니다." >&2
    cleanup_status=1
  fi

  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

printf '\n[observability 1/8] focused unit contracts\n'
python3 -m unittest scripts/backup_tools/test_backup_artifact.py
python3 -m unittest scripts/status_tools/test_production_status.py

printf '\n[observability 2/8] exact-head runtime images\n'
docker build --progress plain --no-cache --pull \
  --tag "$api_image" --file "$ROOT_DIR/infra/docker/api.Dockerfile" "$ROOT_DIR"
docker build --progress plain --no-cache --pull \
  --tag "$web_image" --file "$ROOT_DIR/infra/docker/web.Dockerfile" "$ROOT_DIR"
"${compose[@]}" config --quiet

printf '\n[observability 3/8] strict synthetic backup source\n'
python3 "$BACKUP_HELPER" validate-backup-dir \
  --repo-root "$ROOT_DIR" --path "$backup_directory" >/dev/null
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
stem="$(python3 "$BACKUP_HELPER" new-stem \
  --created-at "$created_at" --schema-version 8)"
staging_directory="$backup_directory/.our-ledger_backup_$stem.partial"
dump_filename="$stem.dump"
mkdir -m 700 "$staging_directory"
printf 'PGDMPsynthetic-observability-archive' \
  > "$staging_directory/$dump_filename"
chmod 600 "$staging_directory/$dump_filename"
python3 "$BACKUP_HELPER" fsync-dump \
  --backup-dir "$backup_directory" \
  --staging-dir "$staging_directory" \
  --dump-filename "$dump_filename"
python3 "$BACKUP_HELPER" write-sidecars \
  --backup-dir "$backup_directory" \
  --staging-dir "$staging_directory" \
  --dump-filename "$dump_filename" \
  --created-at "$created_at" \
  --schema-version 8 \
  --pg-dump-version 'pg_dump (PostgreSQL) 18.6' \
  --postgres-server-version 18.6
python3 "$BACKUP_HELPER" commit \
  --backup-dir "$backup_directory" \
  --staging-dir "$staging_directory" \
  --final-bundle-name "$stem.backup" >/dev/null
mkdir -m 700 "$backup_directory/invalid.backup"
mkdir -m 700 "$backup_directory/.synthetic.partial"
printf 'synthetic foreign inventory entry\n' > "$backup_directory/operator-note.txt"
chmod 600 "$backup_directory/operator-note.txt"

backup_fingerprint() {
  python3 - "$backup_directory" <<'PY'
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*")):
    relative = str(path.relative_to(root)).encode()
    digest.update(relative)
    digest.update(b"d" if path.is_dir() else b"f")
    if path.is_file():
        digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}
backup_before="$(backup_fingerprint)"

printf '\n[observability 4/8] disposable migration and production-like stack\n'
"${compose[@]}" up --detach --wait --wait-timeout 120 postgres
"${compose[@]}" run --rm --no-deps api-migration \
  > "$status_root/candidate-migration.log" 2>&1
if [[ "$(grep -Fxc 'migration-validation: success' \
  "$status_root/candidate-migration.log")" != "1" ]]; then
  echo "Observability fixture candidate migration marker가 올바르지 않습니다." >&2
  exit 1
fi
if grep -Fq -- "$runtime_password" "$status_root/candidate-migration.log"; then
  echo "Observability candidate migration log에 synthetic credential이 노출됐습니다." >&2
  exit 1
fi
if grep -Fq 'jdbc:postgresql://' "$status_root/candidate-migration.log"; then
  echo "Observability candidate migration success output에 connection URL이 노출됐습니다." >&2
  exit 1
fi
"${compose[@]}" up --detach --wait --wait-timeout 240
published_address="$("${compose[@]}" port web 8080)"
if [[ "$published_address" != 127.0.0.1:* ]]; then
  echo "Observability Web origin이 loopback에만 publish되지 않았습니다." >&2
  exit 1
fi
public_status="$(curl --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  --output "$status_root/public-actuator.body" \
  --write-out '%{http_code}' \
  "http://$published_address/actuator/health/operations")"
if [[ "$public_status" != "404" ]] \
  || grep -q '"recurringScheduler"' "$status_root/public-actuator.body"; then
  echo "Public origin에서 internal operations health가 차단되지 않았습니다." >&2
  exit 1
fi

snapshot_file="$status_root/status.json"
snapshot_error_file="$status_root/status-error.log"
collect_snapshot() {
  "$ROOT_DIR/scripts/production-status.sh" \
    --project-name "$project_name" \
    --env-file "$env_file" \
    --backup-dir "$backup_directory" \
    > "$snapshot_file" 2> "$snapshot_error_file"
}

snapshot_matches() {
  local mode="$1"
  python3 - "$snapshot_file" "$mode" "$status_root" <<'PY'
import json
from pathlib import Path
import sys

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    mode = sys.argv[2]
    private_root = sys.argv[3]
    assert set(value) == {
        "formatVersion", "observedAt", "services", "origin",
        "recurring", "backup", "filesystem",
    }
    if mode in {"base", "occurrence", "rule-failure", "reset"}:
        assert all(item["state"] == "RUNNING" for item in value["services"].values())
        assert all(item["health"] == "HEALTHY" for item in value["services"].values())
        assert value["origin"] == {"reachable": True, "healthzStatus": 200}
        assert value["backup"]["markerState"] == "VALID"
        assert value["backup"]["inventory"] == {
            "valid": 1, "invalid": 1, "incomplete": 1, "foreign": 1,
        }
        assert value["filesystem"]["state"] == "AVAILABLE"
    if mode == "base":
        assert value["recurring"]["reachable"] is True
        assert value["recurring"]["status"] == "UP"
        assert value["recurring"]["pollCountSinceStart"] >= 1
    elif mode == "occurrence":
        assert value["recurring"]["status"] == "UP"
        assert value["recurring"]["lastAdvancedOccurrenceCount"] >= 1
    elif mode == "rule-failure":
        assert value["recurring"]["status"] == "UP"
        assert value["recurring"]["lastPollSucceeded"] is True
        assert value["recurring"]["lastPollRuleFailureCount"] >= 1
        assert value["recurring"]["totalRuleFailureCountSinceStart"] >= 1
    elif mode == "unreachable":
        assert value["services"]["api"]["state"] == "EXITED"
        assert value["recurring"]["reachable"] is False
        assert value["recurring"]["status"] == "UNREACHABLE"
    elif mode == "reset":
        assert value["recurring"]["reachable"] is True
        assert value["recurring"]["status"] == "UNKNOWN"
        assert value["recurring"]["pollCountSinceStart"] == 0
        assert value["recurring"]["lastPollSucceeded"] is None
    encoded = json.dumps(value, ensure_ascii=False)
    for forbidden in (
        "backup-owner@example.test",
        "Synthetic broken recurring rule",
        private_root,
    ):
        assert forbidden not in encoded
except Exception:
    raise SystemExit(1)
PY
}

wait_for_snapshot() {
  local mode="$1"
  local attempts="$2"
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if collect_snapshot && snapshot_matches "$mode"; then
      return 0
    fi
    sleep 1
  done
  echo "Observability snapshot 전이가 완료되지 않았습니다: $mode" >&2
  if [[ -s "$snapshot_error_file" ]]; then
    sed -n '1p' "$snapshot_error_file" >&2
  elif [[ -s "$snapshot_file" ]]; then
    python3 - "$snapshot_file" >&2 <<'PY'
import json
from pathlib import Path
import sys

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    summary = {
        "services": value.get("services"),
        "origin": value.get("origin"),
        "recurring": {
            key: (value.get("recurring") or {}).get(key)
            for key in (
                "reachable", "status", "pollCountSinceStart",
                "lastPollSucceeded", "lastAdvancedOccurrenceCount",
                "lastPollRuleFailureCount",
            )
        },
        "backup": {
            key: (value.get("backup") or {}).get(key)
            for key in ("markerState", "inventory")
        },
        "filesystem": {
            "state": (value.get("filesystem") or {}).get("state")
        },
    }
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
except Exception:
    print("snapshot diagnostic summary를 생성할 수 없습니다.")
PY
  fi
  return 1
}

wait_for_snapshot base 30

printf '\n[observability 5/8] recurring success and isolated rule failure\n'
"${compose[@]}" exec -T postgres \
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  < "$ROOT_DIR/scripts/backup_tools/fixture.sql" >/dev/null
"${compose[@]}" exec -T postgres \
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --command "
    UPDATE recurring_transactions
    SET active = TRUE,
        frequency = 'DAILY',
        interval_value = 1,
        start_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date - 1,
        next_recurrence_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date - 1
    WHERE id = 7001;
  " >/dev/null
wait_for_snapshot occurrence 30

"${compose[@]}" exec -T postgres \
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --command "
    INSERT INTO recurring_transactions (
      id, household_id, name, type, amount, scope, owner_member_id,
      payer_member_id, category_id, memo, frequency, interval_value,
      start_date, end_date, scheduled_local_time, auto_post, active,
      next_recurrence_date, version, created_by, updated_by
    )
    SELECT
      7002, household_id, 'Synthetic broken recurring rule', type, amount,
      scope, owner_member_id, payer_member_id, category_id, memo,
      'DAILY', 1,
      (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date - 1,
      NULL, scheduled_local_time, TRUE, TRUE,
      (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date - 1,
      0, created_by, updated_by
    FROM recurring_transactions
    WHERE id = 7001;
  " >/dev/null
wait_for_snapshot rule-failure 30

printf '\n[observability 6/8] HttpFetch response/network contract\n'
api_non_success="$("${compose[@]}" exec -T api \
  java -cp /opt/healthcheck HttpFetch http://127.0.0.1:8080/api)"
if [[ "$api_non_success" != 401$'\n'*'AUTHENTICATION_REQUIRED'* ]]; then
  echo "HttpFetch가 non-200 status/body를 구분하지 못했습니다." >&2
  exit 1
fi
if "${compose[@]}" exec -T api \
  java -cp /opt/healthcheck HttpHealthCheck http://127.0.0.1:8080/api \
  >/dev/null 2>&1; then
  echo "기존 HttpHealthCheck가 non-200을 성공 처리했습니다." >&2
  exit 1
fi
if "${compose[@]}" exec -T api \
  java -cp /opt/healthcheck HttpFetch http://127.0.0.1:1/unreachable \
  >/dev/null 2>&1; then
  echo "HttpFetch가 network failure를 성공 처리했습니다." >&2
  exit 1
fi

printf '\n[observability 7/8] unavailable and process-local reset\n'
"${compose[@]}" stop --timeout 45 api >/dev/null
wait_for_snapshot unreachable 15

export OUR_LEDGER_RECURRING_INITIAL_DELAY_MS=60000
"${compose[@]}" up --detach --no-deps --force-recreate api >/dev/null
api_id="$("${compose[@]}" ps --quiet api)"
for _ in $(seq 1 90); do
  api_health="$(docker inspect --format \
    '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$api_id")"
  if [[ "$api_health" == "healthy" ]]; then
    break
  fi
  sleep 1
done
if [[ "${api_health:-}" != "healthy" ]]; then
  echo "API 재생성 뒤 readiness가 회복되지 않았습니다." >&2
  exit 1
fi
wait_for_snapshot reset 15

backup_after="$(backup_fingerprint)"
if [[ "$backup_after" != "$backup_before" ]]; then
  echo "Read-only status 관측 중 backup directory가 변경됐습니다." >&2
  exit 1
fi

printf '\n[observability 8/8] stable JSON and residue contract\n'
python3 -m json.tool "$snapshot_file" >/dev/null

echo "Observability/status 검증을 통과했습니다."
