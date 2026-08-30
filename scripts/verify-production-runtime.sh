#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.prod.yaml"
FIXTURE_SQL="$ROOT_DIR/scripts/backup_tools/fixture.sql"
STATE_SQL="$ROOT_DIR/scripts/backup_tools/state-fingerprint.sql"

if ! command -v docker >/dev/null 2>&1 \
  || ! docker compose version >/dev/null 2>&1 \
  || ! command -v python3 >/dev/null 2>&1; then
  echo "Docker Compose와 Python 3을 사용할 수 없습니다." >&2
  exit 1
fi

project_name="our-ledger-runtime-$(date +%s)-$$"
api_image="our-ledger-api:$project_name"
web_image="our-ledger-web:$project_name"
runtime_temp_root="${TMPDIR:-/tmp}"
runtime_temp_dir="$(mktemp -d "$runtime_temp_root/our-ledger-runtime.XXXXXX")"
runtime_password="runtime-only-$project_name"
api_image_probe="$project_name-api-image-probe"

case "$runtime_temp_dir" in
  "$runtime_temp_root"/our-ledger-runtime.*) ;;
  *)
    echo "검증 임시 directory 경계가 올바르지 않습니다." >&2
    exit 1
    ;;
esac

compose=(docker compose --project-name "$project_name" --env-file /dev/null -f "$COMPOSE_FILE")

cleanup() {
  local original_status=$?
  local cleanup_status=0
  local container_residue=""
  local image_residue=""
  local network_residue=""
  local volume_residue=""

  trap - EXIT HUP INT TERM
  set +e

  "${compose[@]}" down --volumes --remove-orphans --timeout 45 >/dev/null 2>&1
  docker rm --force "$api_image_probe" >/dev/null 2>&1 || true
  docker image rm "$api_image" "$web_image" >/dev/null 2>&1 || true

  container_residue="$(docker ps --all --quiet --filter "label=com.docker.compose.project=$project_name")"
  network_residue="$(docker network ls --quiet --filter "label=com.docker.compose.project=$project_name")"
  volume_residue="$(docker volume ls --quiet --filter "label=com.docker.compose.project=$project_name")"
  if docker image inspect "$api_image" >/dev/null 2>&1 \
    || docker image inspect "$web_image" >/dev/null 2>&1; then
    image_residue="present"
  fi
  if [[ -n "$container_residue" || -n "$network_residue" \
    || -n "$volume_residue" || -n "$image_residue" ]]; then
    echo "고유 production 검증 project의 Docker resource가 남았습니다: $project_name" >&2
    cleanup_status=1
  fi

  rm -rf -- "$runtime_temp_dir"

  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

run_bounded() {
  local log_path="$1"
  shift
  python3 - "$log_path" "$@" <<'PY'
from pathlib import Path
import subprocess
import sys

log_path = Path(sys.argv[1])
try:
    with log_path.open("wb") as output:
        completed = subprocess.run(
            sys.argv[2:],
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=240,
            check=False,
        )
except subprocess.TimeoutExpired:
    raise SystemExit(124)
raise SystemExit(completed.returncode)
PY
}

assert_log_safe() {
  local log_path="$1"
  local forbidden
  for forbidden in \
    "$runtime_password" \
    "$CLOUDFLARE_ACCESS_AUDIENCE" \
    "candidate-migration@example.test"; do
    if grep -Fq -- "$forbidden" "$log_path"; then
      echo "migration 검증 log에 credential/PII sentinel이 노출됐습니다." >&2
      exit 1
    fi
  done
}

expect_bounded_failure() {
  local label="$1"
  local log_path="$2"
  local failure_status
  shift 2
  if run_bounded "$log_path" "$@"; then
    echo "$label failure path가 성공으로 처리됐습니다." >&2
    exit 1
  else
    failure_status=$?
  fi
  if [[ "$failure_status" == "124" ]]; then
    echo "$label failure path가 deterministic nonzero 대신 timeout됐습니다." >&2
    exit 1
  fi
  assert_log_safe "$log_path"
}

run_candidate_migration() {
  local log_path="$1"
  shift
  run_bounded "$log_path" \
    "${compose[@]}" run --rm --no-deps "$@" api-migration
  assert_log_safe "$log_path"
  if [[ "$(grep -Fxc 'migration-validation: success' "$log_path")" != "1" ]]; then
    echo "candidate migration success marker가 정확히 한 번 기록되지 않았습니다." >&2
    exit 1
  fi
  if grep -Fq 'Tomcat started' "$log_path"; then
    echo "candidate migration process가 HTTP server를 시작했습니다." >&2
    exit 1
  fi
  if grep -Fq 'jdbc:postgresql://' "$log_path"; then
    echo "candidate migration success output에 connection URL이 노출됐습니다." >&2
    exit 1
  fi
}

postgres_query() {
  local database_name="$1"
  local sql="$2"
  "${compose[@]}" exec -T postgres \
    psql --username "$POSTGRES_USER" --dbname "$database_name" \
      --tuples-only --no-align --set ON_ERROR_STOP=1 --command "$sql"
}

create_database() {
  local database_name="$1"
  "${compose[@]}" exec -T postgres \
    createdb --username "$POSTGRES_USER" "$database_name"
}

fixture_fingerprint() {
  "${compose[@]}" exec -T postgres sh -ceu '
    exec psql -X \
      --username "$POSTGRES_USER" \
      --dbname "$POSTGRES_DB" \
      --tuples-only \
      --no-align \
      --set ON_ERROR_STOP=1
  ' < "$STATE_SQL"
}

required_environment=(
  OUR_LEDGER_WEB_IMAGE
  OUR_LEDGER_API_IMAGE
  OUR_LEDGER_ORIGIN_PORT
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  CLOUDFLARE_ACCESS_ISSUER
  CLOUDFLARE_ACCESS_JWK_SET_URI
  CLOUDFLARE_ACCESS_AUDIENCE
)

without_required_environment=(env)
for variable_name in "${required_environment[@]}"; do
  without_required_environment+=("-u" "$variable_name")
done

printf '\n[production 1/13] required environment fail-closed\n'
if "${without_required_environment[@]}" \
  docker compose --project-name "$project_name" --env-file /dev/null -f "$COMPOSE_FILE" \
  config --quiet >/dev/null 2>&1; then
  echo "필수 production 환경변수 없이 Compose render가 성공했습니다." >&2
  exit 1
fi

production_environment=(env \
  OUR_LEDGER_WEB_IMAGE="$web_image" \
  OUR_LEDGER_API_IMAGE="$api_image" \
  OUR_LEDGER_ORIGIN_PORT=0 \
  POSTGRES_DB=our_ledger_runtime \
  POSTGRES_USER=our_ledger_runtime \
  POSTGRES_PASSWORD="$runtime_password" \
  CLOUDFLARE_ACCESS_ISSUER=https://runtime.cloudflareaccess.example \
  CLOUDFLARE_ACCESS_JWK_SET_URI=https://runtime.cloudflareaccess.example/certs \
  CLOUDFLARE_ACCESS_AUDIENCE=runtime-audience)

for variable_name in "${required_environment[@]}"; do
  if "${production_environment[@]}" "$variable_name=" \
    docker compose --project-name "$project_name" --env-file /dev/null -f "$COMPOSE_FILE" \
    config --quiet >/dev/null 2>&1; then
    echo "빈 필수 production 환경변수로 Compose render가 성공했습니다: $variable_name" >&2
    exit 1
  fi
done

export OUR_LEDGER_WEB_IMAGE="$web_image"
export OUR_LEDGER_API_IMAGE="$api_image"
export OUR_LEDGER_ORIGIN_PORT=0
export POSTGRES_DB=our_ledger_runtime
export POSTGRES_USER=our_ledger_runtime
export POSTGRES_PASSWORD="$runtime_password"
export CLOUDFLARE_ACCESS_ISSUER=https://runtime.cloudflareaccess.example
export CLOUDFLARE_ACCESS_JWK_SET_URI=https://runtime.cloudflareaccess.example/cdn-cgi/access/certs
export CLOUDFLARE_ACCESS_AUDIENCE=runtime-audience
export OUR_LEDGER_EXPECTED_COMPOSE_PROJECT="$project_name"

"${compose[@]}" --profile migration --profile bootstrap config --format json \
  | python3 "$ROOT_DIR/scripts/check-production-compose.py"

printf '\n[production 2/13] clean immutable image build\n'
docker build --progress plain --no-cache --pull --tag "$api_image" --file "$ROOT_DIR/infra/docker/api.Dockerfile" "$ROOT_DIR"
docker build --progress plain --no-cache --pull --tag "$web_image" --file "$ROOT_DIR/infra/docker/web.Dockerfile" "$ROOT_DIR"

printf '\n[production 3/13] runtime image contents and Nginx config\n'
docker create --name "$api_image_probe" "$api_image" >/dev/null
docker export "$api_image_probe" | tar -tf - > "$runtime_temp_dir/api-image-contents.txt"
docker rm "$api_image_probe" >/dev/null

for required_path in \
  app/app.jar \
  opt/healthcheck/HttpHealthCheck.class \
  opt/healthcheck/HttpFetch.class; do
  if ! awk -v target="$required_path" '
    $0 == target || $0 == "./" target { found = 1 }
    END { exit !found }
  ' "$runtime_temp_dir/api-image-contents.txt"; then
    echo "API runtime image에 필수 artifact가 없습니다: $required_path" >&2
    exit 1
  fi
done

for forbidden_path in \
  bin/sh \
  bin/bash \
  usr/bin/apt \
  usr/bin/apt-get \
  usr/bin/dpkg \
  sbin/apk \
  usr/bin/yum \
  usr/bin/dnf; do
  if ! awk -v target="$forbidden_path" '
    $0 == target || $0 == "./" target { exit 1 }
  ' "$runtime_temp_dir/api-image-contents.txt"; then
    echo "API runtime image에 shell/package manager가 포함됐습니다: $forbidden_path" >&2
    exit 1
  fi
done

if ! awk '
  {
    path = tolower($0)
    if (path ~ /(^|\/)(gradle|gradlew)(\/|$)/ ||
        path ~ /(^|\/)workspace\// ||
        path ~ /\.java$/) {
      exit 1
    }
  }
' "$runtime_temp_dir/api-image-contents.txt"; then
  echo "API runtime image에 build tool/source가 포함됐습니다." >&2
  exit 1
fi

docker run --rm --entrypoint java "$api_image" -version
docker run --rm --entrypoint /bin/sh "$web_image" -c '
  set -eu
  test "$(id -u)" != "0"
  test -f /usr/share/nginx/html/index.html
  command -v nginx >/dev/null
  ! command -v node >/dev/null
  ! command -v npm >/dev/null
  ! test -e /workspace
  ! test -e /usr/share/nginx/html/50x.html
  ! find /usr/share/nginx/html -type f \( -name "*.ts" -o -name "*.tsx" \) -print -quit | read -r _
'
docker run --rm --add-host api:127.0.0.1 --entrypoint nginx "$web_image" -t

nginx_config="$(docker run --rm --entrypoint /bin/sh "$web_image" -c 'cat /etc/nginx/nginx.conf')"
for required_directive in \
  'proxy_set_header Cf-Access-Jwt-Assertion' \
  'proxy_set_header Host' \
  'proxy_set_header X-Forwarded-For' \
  'proxy_set_header X-Forwarded-Proto' \
  'proxy_set_header X-Request-ID' \
  'proxy_buffering off'; do
  if [[ "$nginx_config" != *"$required_directive"* ]]; then
    echo "Nginx proxy 계약이 누락됐습니다: $required_directive" >&2
    exit 1
  fi
done
if [[ "$nginx_config" == *"proxy_hide_header Content-Disposition"* ]]; then
  echo "Nginx가 API Content-Disposition을 숨기고 있습니다." >&2
  exit 1
fi

api_history="$(docker history --no-trunc "$api_image")"
web_history="$(docker history --no-trunc "$web_image")"
if [[ "$api_history" == *"$runtime_password"* || "$web_history" == *"$runtime_password"* ]]; then
  echo "합성 runtime credential이 image history에 포함됐습니다." >&2
  exit 1
fi

printf '\n[production 4/13] normal production startup cannot mutate a clean schema\n'
"${compose[@]}" up --detach --wait --wait-timeout 120 postgres

expect_bounded_failure \
  "normal production clean-schema startup" \
  "$runtime_temp_dir/normal-clean-schema.log" \
  "${compose[@]}" run --rm --no-deps api
expect_bounded_failure \
  "normal production Flyway override" \
  "$runtime_temp_dir/normal-flyway-override.log" \
  "${compose[@]}" run --rm --no-deps \
    --env SPRING_FLYWAY_ENABLED=true \
    api

clean_public_table_count="$(postgres_query "$POSTGRES_DB" \
  "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")"
if [[ "$clean_public_table_count" != "0" ]]; then
  echo "normal production startup이 clean schema를 변경했습니다." >&2
  exit 1
fi

printf '\n[production 5/13] one-shot candidate migration and JPA validation\n'
run_candidate_migration "$runtime_temp_dir/migration-clean.log"

flyway_versions="$(postgres_query "$POSTGRES_DB" \
  "SELECT string_agg(version, ',' ORDER BY installed_rank) FROM flyway_schema_history WHERE success")"
if [[ "$flyway_versions" != "1,2,3,4,5,6,7,8" ]]; then
  echo "candidate migration history가 V1-V8 clean contract와 다릅니다: $flyway_versions" >&2
  exit 1
fi
empty_domain_counts="$(postgres_query "$POSTGRES_DB" \
  "SELECT (SELECT COUNT(*) FROM users) || ':' || (SELECT COUNT(*) FROM households)")"
if [[ "$empty_domain_counts" != "0:0" ]]; then
  echo "candidate migration이 bootstrap data를 생성했습니다." >&2
  exit 1
fi
if [[ -n "$(docker ps --all --quiet \
  --filter "label=com.docker.compose.project=$project_name" \
  --filter "label=com.docker.compose.service=api-migration")" ]]; then
  echo "one-shot candidate migration container가 남았습니다." >&2
  exit 1
fi

printf '\n[production 6/13] migration failure matrix\n'
corrupt_database=our_ledger_runtime_corrupt
damaged_database=our_ledger_runtime_damaged
create_database "$corrupt_database"
create_database "$damaged_database"

run_candidate_migration \
  "$runtime_temp_dir/migration-corrupt-seed.log" \
  --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$corrupt_database"
postgres_query "$corrupt_database" \
  "UPDATE flyway_schema_history SET success = false WHERE version = '8'" >/dev/null
expect_bounded_failure \
  "failed Flyway history" \
  "$runtime_temp_dir/migration-corrupt.log" \
  "${compose[@]}" run --rm --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$corrupt_database" \
    api-migration

run_candidate_migration \
  "$runtime_temp_dir/migration-damaged-seed.log" \
  --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$damaged_database"
postgres_query "$damaged_database" "ALTER TABLE users DROP COLUMN status" >/dev/null
expect_bounded_failure \
  "JPA schema validation" \
  "$runtime_temp_dir/migration-damaged.log" \
  "${compose[@]}" run --rm --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$damaged_database" \
    api-migration

expect_bounded_failure \
  "unreachable database" \
  "$runtime_temp_dir/migration-unreachable.log" \
  "${compose[@]}" run --rm --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:1/$POSTGRES_DB" \
    api-migration

schema_authority_before="$(postgres_query "$POSTGRES_DB" \
  "SELECT string_agg(version || ':' || checksum, ',' ORDER BY installed_rank) FROM flyway_schema_history")"
expect_bounded_failure \
  "migration without production profile" \
  "$runtime_temp_dir/migration-profile.log" \
  "${compose[@]}" run --rm --no-deps \
    --env SPRING_PROFILES_ACTIVE=migration \
    api-migration
expect_bounded_failure \
  "migration with reversed profile authority" \
  "$runtime_temp_dir/migration-profile-order.log" \
  "${compose[@]}" run --rm --no-deps \
    --env SPRING_PROFILES_ACTIVE=migration,production \
    api-migration
expect_bounded_failure \
  "migration with bootstrap enabled" \
  "$runtime_temp_dir/migration-bootstrap.log" \
  "${compose[@]}" run --rm --no-deps \
    --env OUR_LEDGER_BOOTSTRAP_ENABLED=true \
    api-migration
expect_bounded_failure \
  "migration with recurring scheduler enabled" \
  "$runtime_temp_dir/migration-scheduler.log" \
  "${compose[@]}" run --rm --no-deps \
    --env OUR_LEDGER_RECURRING_SCHEDULER_ENABLED=true \
    api-migration
expect_bounded_failure \
  "migration with Flyway disabled" \
  "$runtime_temp_dir/migration-flyway-disabled.log" \
  "${compose[@]}" run --rm --no-deps \
    --env SPRING_FLYWAY_ENABLED=false \
    api-migration
schema_authority_after="$(postgres_query "$POSTGRES_DB" \
  "SELECT string_agg(version || ':' || checksum, ',' ORDER BY installed_rank) FROM flyway_schema_history")"
if [[ "$schema_authority_after" != "$schema_authority_before" ]]; then
  echo "invalid migration invocation이 schema authority를 변경했습니다." >&2
  exit 1
fi

printf '\n[production 7/13] idempotent rerun without bootstrap or scheduling\n'
"${compose[@]}" exec -T postgres sh -ceu '
  exec psql -X \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1
' < "$FIXTURE_SQL"
postgres_query "$POSTGRES_DB" \
  "UPDATE recurring_transactions
      SET active = true,
          next_recurrence_date = DATE '2026-08-01',
          scheduled_local_time = TIME '00:00:00'
    WHERE id = 7001" >/dev/null
fixture_before="$(fixture_fingerprint)"
run_candidate_migration "$runtime_temp_dir/migration-idempotent.log"
fixture_after="$(fixture_fingerprint)"
if [[ "$fixture_after" != "$fixture_before" ]]; then
  echo "candidate migration rerun이 application data 또는 schedule state를 변경했습니다." >&2
  exit 1
fi
postgres_query "$POSTGRES_DB" \
  "UPDATE recurring_transactions
      SET active = false,
          next_recurrence_date = NULL
    WHERE id = 7001" >/dev/null

printf '\n[production 8/13] normal production stack startup after migration\n'
normal_schema_before="$(postgres_query "$POSTGRES_DB" \
  "SELECT string_agg(version || ':' || checksum, ',' ORDER BY installed_rank) FROM flyway_schema_history")"
"${compose[@]}" up --detach --wait --wait-timeout 240

web_id="$("${compose[@]}" ps --quiet web)"
api_id="$("${compose[@]}" ps --quiet api)"
postgres_id="$("${compose[@]}" ps --quiet postgres)"
if [[ -z "$web_id" || -z "$api_id" || -z "$postgres_id" ]]; then
  echo "production 검증 container ID를 확인할 수 없습니다." >&2
  exit 1
fi

docker inspect "$web_id" "$api_id" "$postgres_id" \
  | python3 "$ROOT_DIR/scripts/check-production-runtime.py" "$project_name"

published_address="$("${compose[@]}" port web 8080)"
if [[ "$published_address" != 127.0.0.1:* ]]; then
  echo "web runtime publish 주소가 loopback이 아닙니다." >&2
  exit 1
fi
runtime_origin="http://$published_address"

request_path() {
  local request_name="$1"
  local request_path_value="$2"
  shift 2
  runtime_status="$(curl --silent --show-error \
    --connect-timeout 5 --max-time 30 \
    --dump-header "$runtime_temp_dir/$request_name.headers" \
    --output "$runtime_temp_dir/$request_name.body" \
    --write-out '%{http_code}' \
    "$@" "$runtime_origin$request_path_value")"
}

assert_status() {
  local expected="$1"
  local label="$2"
  if [[ "$runtime_status" != "$expected" ]]; then
    echo "$label HTTP status가 $expected가 아닙니다: $runtime_status" >&2
    exit 1
  fi
}

assert_header_contains() {
  local request_name="$1"
  local header_name="$2"
  local expected_value="$3"
  local expected_value_lower
  local header_value
  expected_value_lower="$(printf '%s' "$expected_value" | tr '[:upper:]' '[:lower:]')"
  header_value="$(awk -v key="$header_name" '
    index(tolower($0), tolower(key) ":") == 1 {
      sub(/^[^:]+:[[:space:]]*/, "", $0)
      gsub(/\r/, "", $0)
      print tolower($0)
    }
  ' "$runtime_temp_dir/$request_name.headers")"
  if [[ "$header_value" != *"$expected_value_lower"* ]]; then
    echo "$request_name 응답의 $header_name header가 $expected_value를 포함하지 않습니다." >&2
    exit 1
  fi
}

printf '\n[production 9/13] static, SPA and cache policy\n'
request_path root /
assert_status 200 "root"
if [[ "$(<"$runtime_temp_dir/root.body")" != *'<div id="root"></div>'* ]]; then
  echo "root 응답이 production frontend index가 아닙니다." >&2
  exit 1
fi
assert_header_contains root Cache-Control no-store

asset_path="$(sed -nE 's/.*(\/assets\/[^" ]+\.(js|css)).*/\1/p' "$runtime_temp_dir/root.body" | sed -n '1p')"
if [[ -z "$asset_path" ]]; then
  echo "production index에서 hashed asset을 찾지 못했습니다." >&2
  exit 1
fi
request_path asset "$asset_path"
assert_status 200 "hashed asset"
assert_header_contains asset Cache-Control max-age=31536000
assert_header_contains asset Cache-Control immutable

request_path spa /calendar?month=2026-08
assert_status 200 "SPA deep link"
if [[ "$(<"$runtime_temp_dir/spa.body")" != *'<div id="root"></div>'* ]]; then
  echo "SPA deep link가 index fallback을 반환하지 않았습니다." >&2
  exit 1
fi
assert_header_contains spa Cache-Control no-store

printf '\n[production 10/13] same-origin API and authentication boundary\n'
request_path api_exact /api
assert_status 401 "exact /api"
assert_header_contains api_exact Content-Type application/json
assert_header_contains api_exact Cache-Control no-store
if [[ "$(<"$runtime_temp_dir/api_exact.body")" != *'AUTHENTICATION_REQUIRED'* ]]; then
  echo "exact /api가 canonical authentication error를 반환하지 않았습니다." >&2
  exit 1
fi

request_path api_accounts /api/v1/accounts
assert_status 401 "unauthenticated API"
assert_header_contains api_accounts Content-Type application/json
assert_header_contains api_accounts Cache-Control no-store
if [[ "$(<"$runtime_temp_dir/api_accounts.body")" != *'AUTHENTICATION_REQUIRED'* ]]; then
  echo "unauthenticated API가 canonical authentication error를 반환하지 않았습니다." >&2
  exit 1
fi

request_path forged_identity /api/v1/accounts \
  --header 'X-Our-Ledger-Local-Identity: forged@example.test'
assert_status 401 "forged local identity"
if [[ "$(<"$runtime_temp_dir/forged_identity.body")" != *'AUTHENTICATION_REQUIRED'* ]]; then
  echo "production에서 forged local identity가 fail-closed되지 않았습니다." >&2
  exit 1
fi

printf '\n[production 11/13] public and internal health boundary\n'
request_path actuator /actuator/health
assert_status 404 "public actuator"
if [[ "$(<"$runtime_temp_dir/actuator.body")" == *'"status"'* ]]; then
  echo "public actuator 응답에 backend health body가 노출됐습니다." >&2
  exit 1
fi

request_path healthz /healthz
assert_status 200 "Nginx healthz"
assert_header_contains healthz Content-Type text/plain
assert_header_contains healthz Cache-Control no-store
if [[ "$(<"$runtime_temp_dir/healthz.body")" != "ok" ]]; then
  echo "Nginx healthz body가 safe static contract와 다릅니다." >&2
  exit 1
fi

server_header="$(awk '
  index(tolower($0), "server:") == 1 {
    sub(/^[^:]+:[[:space:]]*/, "", $0)
    gsub(/\r/, "", $0)
    print $0
  }
' "$runtime_temp_dir/root.headers")"
if [[ "$server_header" == */* ]]; then
  echo "Nginx server version token이 노출됐습니다." >&2
  exit 1
fi

"${compose[@]}" exec -T api \
  java -cp /opt/healthcheck HttpHealthCheck http://127.0.0.1:8080/actuator/health/readiness
operations_response="$("${compose[@]}" exec -T api \
  java -cp /opt/healthcheck HttpFetch http://127.0.0.1:8080/actuator/health/operations)"
if ! python3 -c '
import json
import sys

status, separator, body = sys.stdin.read().partition("\n")
payload = json.loads(body)
assert separator and status == "200"
assert "recurringScheduler" in payload["components"]
' <<< "$operations_response"; then
  echo "HttpFetch가 internal operations status/body를 구분하지 못했습니다." >&2
  exit 1
fi

printf '\n[production 12/13] normal startup and restart schema immutability\n'
normal_schema_after_start="$(postgres_query "$POSTGRES_DB" \
  "SELECT string_agg(version || ':' || checksum, ',' ORDER BY installed_rank) FROM flyway_schema_history")"
if [[ "$normal_schema_after_start" != "$normal_schema_before" ]]; then
  echo "normal production startup이 Flyway history를 변경했습니다." >&2
  exit 1
fi

"${compose[@]}" restart api
for _ in $(seq 1 90); do
  api_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$api_id")"
  if [[ "$api_health" == "healthy" ]]; then
    break
  fi
  sleep 2
done
if [[ "${api_health:-}" != "healthy" ]]; then
  echo "API restart 뒤 readiness가 회복되지 않았습니다." >&2
  exit 1
fi

normal_schema_after_restart="$(postgres_query "$POSTGRES_DB" \
  "SELECT string_agg(version || ':' || checksum, ',' ORDER BY installed_rank) FROM flyway_schema_history")"
if [[ "$normal_schema_after_restart" != "$normal_schema_before" ]]; then
  echo "API restart 뒤 Flyway history가 변경됐습니다." >&2
  exit 1
fi

printf '\n[production 13/13] graceful stop\n'
"${compose[@]}" stop --timeout 45 api
api_exit_code="$(docker inspect --format '{{.State.ExitCode}}' "$api_id")"
if [[ "$api_exit_code" != "0" && "$api_exit_code" != "143" ]]; then
  echo "API graceful stop exit code가 예상 범위가 아닙니다: $api_exit_code" >&2
  exit 1
fi
api_logs="$(docker logs "$api_id" 2>&1)"
if [[ "$api_logs" != *"Commencing graceful shutdown"* \
  || "$api_logs" != *"Graceful shutdown complete"* ]]; then
  echo "Spring graceful shutdown 완료 log를 확인하지 못했습니다." >&2
  exit 1
fi

echo "Production runtime 검증을 통과했습니다."
