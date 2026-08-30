#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.prod.yaml"

if ! command -v docker >/dev/null 2>&1 \
  || ! docker compose version >/dev/null 2>&1 \
  || ! command -v python3 >/dev/null 2>&1 \
  || ! command -v git >/dev/null 2>&1; then
  echo "Docker Compose, Python 3, Git을 사용할 수 없습니다." >&2
  exit 1
fi

git_head="$(git -C "$ROOT_DIR" rev-parse HEAD)"
if [[ ! "$git_head" =~ ^[0-9a-f]{40}$ ]]; then
  echo "bootstrap 검증 Git HEAD가 exact lowercase SHA가 아닙니다." >&2
  exit 1
fi

run_token="$(date +%s)-$$"
project_name="our-ledger-bootstrap-$run_token"
api_image="our-ledger-api:$project_name"
runtime_temp_root="${TMPDIR:-/tmp}"
runtime_temp_dir="$(mktemp -d "$runtime_temp_root/our-ledger-bootstrap.XXXXXX")"
override_file="$runtime_temp_dir/compose.labels.yaml"
runtime_password="synthetic-bootstrap-$run_token"
owner_email="bootstrap-owner-49@example.test"
member_email="bootstrap-member-49@example.test"
owner_name="Issue49OwnerSentinel"
member_name="Issue49MemberSentinel"
household_name="Issue49HouseholdSentinel"

case "$runtime_temp_dir" in
  "$runtime_temp_root"/our-ledger-bootstrap.*) ;;
  *)
    echo "bootstrap 검증 임시 directory 경계가 올바르지 않습니다." >&2
    exit 1
    ;;
esac

chmod 700 "$runtime_temp_dir"

python3 -B - "$override_file" "$git_head" <<'PY'
from pathlib import Path
import sys

target = Path(sys.argv[1])
git_head = sys.argv[2]
labels = {
    "io.homeserver.cleanup.environment": "development",
    "io.homeserver.cleanup.project": "our-ledger",
    "io.homeserver.cleanup.task": "issue-49-production-household-bootstrap",
    "io.homeserver.cleanup.lifecycle": "task",
    "io.homeserver.cleanup.retain": "false",
    "io.homeserver.cleanup.git-head": git_head,
}
lines = ["services:"]
for service in ("web", "api", "api-migration", "api-bootstrap", "postgres"):
    lines.extend((f"  {service}:", "    labels:"))
    for key, value in labels.items():
        lines.append(f'      {key}: "{value}"')
for group, names in (
    ("networks", ("application", "database")),
    ("volumes", ("postgres-data",)),
):
    lines.append(f"{group}:")
    for name in names:
        lines.extend((f"  {name}:", "    labels:"))
        for key, value in labels.items():
            lines.append(f'      {key}: "{value}"')
target.write_text("\n".join(lines) + "\n", encoding="utf-8")
target.chmod(0o600)
PY

python3 -B - \
  "$runtime_temp_dir" \
  "$owner_email" \
  "$member_email" \
  "$owner_name" \
  "$member_name" \
  "$household_name" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
owner_email, member_email, owner_name, member_name, household_name = sys.argv[2:]
valid = {
    "formatVersion": 1,
    "householdName": household_name,
    "owner": {"email": owner_email, "displayName": owner_name},
    "member": {"email": member_email, "displayName": member_name},
}

payloads = {
    "valid.json": json.dumps(valid, ensure_ascii=False),
    "empty.json": "",
    "malformed.json": '{"formatVersion":',
    "unknown.json": json.dumps({**valid, "unknown": True}, ensure_ascii=False),
    "duplicate.json": (
        '{"formatVersion":1,"formatVersion":1,'
        f'"householdName":"{household_name}",'
        f'"owner":{{"email":"{owner_email}","displayName":"{owner_name}"}},'
        f'"member":{{"email":"{member_email}","displayName":"{member_name}"}}}}'
    ),
    "missing.json": json.dumps({key: value for key, value in valid.items() if key != "member"}, ensure_ascii=False),
    "null.json": json.dumps({**valid, "householdName": None}, ensure_ascii=False),
    "wrong-type.json": json.dumps({**valid, "formatVersion": "1"}, ensure_ascii=False),
    "trailing.json": json.dumps(valid, ensure_ascii=False) + "{}",
    "same-email.json": json.dumps(
        {**valid, "member": {"email": owner_email.upper(), "displayName": member_name}},
        ensure_ascii=False,
    ),
}
for name, value in payloads.items():
    path = root / name
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
(root / "oversize.json").write_bytes(b" " * 8193)
(root / "oversize.json").chmod(0o600)
(root / "invalid-utf8.json").write_bytes(bytes((0xC3, 0x28)))
(root / "invalid-utf8.json").chmod(0o600)
PY

export OUR_LEDGER_WEB_IMAGE="our-ledger-web:unused-$project_name"
export OUR_LEDGER_API_IMAGE="$api_image"
export OUR_LEDGER_ORIGIN_PORT=0
export POSTGRES_DB=our_ledger_bootstrap
export POSTGRES_USER=our_ledger_bootstrap
export POSTGRES_PASSWORD="$runtime_password"
export CLOUDFLARE_ACCESS_ISSUER=https://bootstrap.cloudflareaccess.example
export CLOUDFLARE_ACCESS_JWK_SET_URI=https://bootstrap.cloudflareaccess.example/certs
export CLOUDFLARE_ACCESS_AUDIENCE=bootstrap-audience
export OUR_LEDGER_EXPECTED_COMPOSE_PROJECT="$project_name"

compose=(
  docker compose
  --project-name "$project_name"
  --env-file /dev/null
  --file "$COMPOSE_FILE"
  --file "$override_file"
  --profile migration
  --profile bootstrap
)

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
  docker image rm "$api_image" >/dev/null 2>&1 || true

  container_residue="$(docker ps --all --quiet --filter "label=com.docker.compose.project=$project_name")"
  network_residue="$(docker network ls --quiet --filter "label=com.docker.compose.project=$project_name")"
  volume_residue="$(docker volume ls --quiet --filter "label=com.docker.compose.project=$project_name")"
  if docker image inspect "$api_image" >/dev/null 2>&1; then
    image_residue="present"
  fi
  if [[ -n "$container_residue" || -n "$network_residue" \
    || -n "$volume_residue" || -n "$image_residue" ]]; then
    echo "bootstrap synthetic Docker resource가 남았습니다: $project_name" >&2
    cleanup_status=1
  fi

  python3 -B - "$runtime_temp_dir" "$runtime_temp_root" <<'PY'
from pathlib import Path
import shutil
import sys

target = Path(sys.argv[1])
root = Path(sys.argv[2])
if target.parent != root or not target.name.startswith("our-ledger-bootstrap."):
    raise SystemExit("bootstrap temporary cleanup boundary differs")
shutil.rmtree(target)
PY

  if (( original_status != 0 )); then
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

run_bounded_input() {
  local log_path="$1"
  local input_path="$2"
  shift 2
  python3 -B - "$log_path" "$input_path" "$@" <<'PY'
from pathlib import Path
import subprocess
import sys

log_path = Path(sys.argv[1])
input_path = Path(sys.argv[2])
try:
    with input_path.open("rb") as input_file, log_path.open("wb") as output:
        completed = subprocess.run(
            sys.argv[3:],
            stdin=input_file,
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
    "$owner_email" \
    "$member_email" \
    "$owner_name" \
    "$member_name" \
    "$household_name" \
    '"formatVersion"' \
    '"householdName"' \
    'householdId' \
    'ownerUserId' \
    'memberUserId' \
    'jdbc:postgresql://'; do
    if grep -Fq -- "$forbidden" "$log_path"; then
      echo "bootstrap 검증 output에 credential/PII/raw input/ID가 노출됐습니다." >&2
      exit 1
    fi
  done
}

expect_failure() {
  local label="$1"
  local log_path="$2"
  local input_path="$3"
  local failure_status
  shift 3
  if run_bounded_input "$log_path" "$input_path" "$@"; then
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

run_candidate_migration() {
  local database_name="$1"
  local log_path="$2"
  run_bounded_input \
    "$log_path" \
    /dev/null \
    "${compose[@]}" run --rm -T --no-deps \
      --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$database_name" \
      api-migration
  assert_log_safe "$log_path"
  if [[ "$(grep -Fxc 'migration-validation: success' "$log_path")" != "1" ]]; then
    echo "candidate migration marker가 정확히 한 번 기록되지 않았습니다." >&2
    exit 1
  fi
}

run_bootstrap_success() {
  local database_name="$1"
  local input_path="$2"
  local expected_marker="$3"
  local log_path="$4"
  run_bounded_input \
    "$log_path" \
    "$input_path" \
    "${compose[@]}" run --rm -T --no-deps \
      --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$database_name" \
      api-bootstrap
  assert_log_safe "$log_path"
  if [[ "$(grep -Fxc "$expected_marker" "$log_path")" != "1" ]]; then
    echo "bootstrap success marker가 정확히 한 번 기록되지 않았습니다: $expected_marker" >&2
    exit 1
  fi
  if grep -Fq 'Tomcat started' "$log_path"; then
    echo "bootstrap one-shot이 HTTP server를 시작했습니다." >&2
    exit 1
  fi
}

bootstrap_fingerprint() {
  local database_name="$1"
  postgres_query "$database_name" "
    SELECT md5(
      COALESCE((SELECT string_agg(row_to_json(u)::text, ',' ORDER BY id) FROM users u), '') || '|' ||
      COALESCE((SELECT string_agg(row_to_json(h)::text, ',' ORDER BY id) FROM households h), '') || '|' ||
      COALESCE((SELECT string_agg(row_to_json(m)::text, ',' ORDER BY id) FROM household_members m), '') || '|' ||
      (SELECT last_value::text || ':' || is_called::text FROM users_id_seq) || '|' ||
      (SELECT last_value::text || ':' || is_called::text FROM households_id_seq) || '|' ||
      (SELECT last_value::text || ':' || is_called::text FROM household_members_id_seq)
    )"
}

schema_fingerprint() {
  local database_name="$1"
  postgres_query "$database_name" \
    "SELECT md5(string_agg(installed_rank || ':' || version || ':' || checksum || ':' || success, ',' ORDER BY installed_rank)) FROM flyway_schema_history"
}

printf '\n[bootstrap 1/12] Compose authority and cleanup labels\n'
"${compose[@]}" config --format json \
  | python3 -B "$ROOT_DIR/scripts/check-production-compose.py"
"${compose[@]}" config --format json \
  | python3 -B -c '
import json
import sys

git_head = sys.argv[1]
config = json.load(sys.stdin)
expected = {
    "io.homeserver.cleanup.environment": "development",
    "io.homeserver.cleanup.project": "our-ledger",
    "io.homeserver.cleanup.task": "issue-49-production-household-bootstrap",
    "io.homeserver.cleanup.lifecycle": "task",
    "io.homeserver.cleanup.retain": "false",
    "io.homeserver.cleanup.git-head": git_head,
}
for group in ("services", "networks", "volumes"):
    for resource in config[group].values():
        if resource.get("labels") != expected:
            raise SystemExit("bootstrap synthetic cleanup labels differ")
' "$git_head"

printf '\n[bootstrap 2/12] same candidate API image build\n'
docker build \
  --progress plain \
  --label io.homeserver.cleanup.environment=development \
  --label io.homeserver.cleanup.project=our-ledger \
  --label io.homeserver.cleanup.task=issue-49-production-household-bootstrap \
  --label io.homeserver.cleanup.lifecycle=task \
  --label io.homeserver.cleanup.retain=false \
  --label "io.homeserver.cleanup.git-head=$git_head" \
  --tag "$api_image" \
  --file "$ROOT_DIR/infra/docker/api.Dockerfile" \
  "$ROOT_DIR"

printf '\n[bootstrap 3/12] unmigrated schema fail-closed\n'
"${compose[@]}" up --detach --wait --wait-timeout 120 postgres
expect_failure \
  "unmigrated bootstrap" \
  "$runtime_temp_dir/unmigrated.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps api-bootstrap
if [[ "$(postgres_query "$POSTGRES_DB" "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")" != "0" ]]; then
  echo "unmigrated bootstrap이 schema/table을 변경했습니다." >&2
  exit 1
fi

printf '\n[bootstrap 4/12] V1-V8 migration without bootstrap data\n'
run_candidate_migration "$POSTGRES_DB" "$runtime_temp_dir/migration.log"
if [[ "$(postgres_query "$POSTGRES_DB" "SELECT string_agg(version, ',' ORDER BY installed_rank) FROM flyway_schema_history WHERE success")" != "1,2,3,4,5,6,7,8" ]]; then
  echo "bootstrap 검증 migration history가 V1-V8 contract와 다릅니다." >&2
  exit 1
fi
if [[ "$(postgres_query "$POSTGRES_DB" "SELECT (SELECT COUNT(*) FROM users) || ':' || (SELECT COUNT(*) FROM households) || ':' || (SELECT COUNT(*) FROM household_members)")" != "0:0:0" ]]; then
  echo "migration mode가 bootstrap data를 생성했습니다." >&2
  exit 1
fi
schema_before_bootstrap="$(schema_fingerprint "$POSTGRES_DB")"

printf '\n[bootstrap 5/12] empty create and exact state\n'
run_bootstrap_success \
  "$POSTGRES_DB" \
  "$runtime_temp_dir/valid.json" \
  "household-bootstrap: created" \
  "$runtime_temp_dir/created.log"
exact_state="$(postgres_query "$POSTGRES_DB" \
  "SELECT
     (SELECT COUNT(*) FROM users) || ':' ||
     (SELECT COUNT(*) FROM households) || ':' ||
     (SELECT COUNT(*) FROM household_members) || ':' ||
     (SELECT string_agg(role, ',' ORDER BY role) FROM household_members) || ':' ||
     (SELECT base_currency || ':' || timezone FROM households)")"
if [[ "$exact_state" != "2:1:2:MEMBER,OWNER:KRW:Asia/Seoul" ]]; then
  echo "bootstrap exact 2/1/2 state 또는 defaults가 계약과 다릅니다." >&2
  exit 1
fi
created_fingerprint="$(bootstrap_fingerprint "$POSTGRES_DB")"

printf '\n[bootstrap 6/12] idempotent exact rerun\n'
run_bootstrap_success \
  "$POSTGRES_DB" \
  "$runtime_temp_dir/valid.json" \
  "household-bootstrap: verified" \
  "$runtime_temp_dir/verified.log"
if [[ "$(bootstrap_fingerprint "$POSTGRES_DB")" != "$created_fingerprint" ]]; then
  echo "bootstrap exact rerun이 rows 또는 identity sequence를 변경했습니다." >&2
  exit 1
fi
if [[ "$(schema_fingerprint "$POSTGRES_DB")" != "$schema_before_bootstrap" ]]; then
  echo "bootstrap mode가 Flyway history를 변경했습니다." >&2
  exit 1
fi
if [[ -n "$(docker ps --all --quiet \
  --filter "label=com.docker.compose.project=$project_name" \
  --filter "label=com.docker.compose.service=api-bootstrap")" ]]; then
  echo "one-shot bootstrap container가 남았습니다." >&2
  exit 1
fi

printf '\n[bootstrap 7/12] strict stdin failure matrix\n'
for input_name in \
  empty malformed oversize unknown duplicate missing null wrong-type trailing same-email invalid-utf8; do
  expect_failure \
    "bootstrap input $input_name" \
    "$runtime_temp_dir/input-$input_name.log" \
    "$runtime_temp_dir/$input_name.json" \
    "${compose[@]}" run --rm -T --no-deps api-bootstrap
done
if [[ "$(bootstrap_fingerprint "$POSTGRES_DB")" != "$created_fingerprint" ]]; then
  echo "invalid bootstrap input이 exact state를 변경했습니다." >&2
  exit 1
fi

printf '\n[bootstrap 8/12] partial, mismatch, and extra state fail-closed\n'
partial_database=our_ledger_bootstrap_partial
mismatch_database=our_ledger_bootstrap_mismatch
extra_database=our_ledger_bootstrap_extra
for database_name in "$partial_database" "$mismatch_database" "$extra_database"; do
  create_database "$database_name"
  run_candidate_migration "$database_name" "$runtime_temp_dir/migration-$database_name.log"
done

postgres_query "$partial_database" \
  "INSERT INTO users(email, display_name, status) VALUES ('partial@example.test', 'Partial', 'ACTIVE')" >/dev/null
partial_before="$(bootstrap_fingerprint "$partial_database")"
expect_failure \
  "partial state" \
  "$runtime_temp_dir/partial.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$partial_database" \
    api-bootstrap
if [[ "$(bootstrap_fingerprint "$partial_database")" != "$partial_before" ]]; then
  echo "partial bootstrap state가 자동 repair됐습니다." >&2
  exit 1
fi

run_bootstrap_success \
  "$mismatch_database" \
  "$runtime_temp_dir/valid.json" \
  "household-bootstrap: created" \
  "$runtime_temp_dir/mismatch-seed.log"
postgres_query "$mismatch_database" \
  "UPDATE household_members SET role = 'MEMBER' WHERE role = 'OWNER';
   UPDATE household_members SET role = 'OWNER'
    WHERE user_id = (SELECT id FROM users WHERE email = '$member_email')" >/dev/null
mismatch_before="$(bootstrap_fingerprint "$mismatch_database")"
expect_failure \
  "membership mismatch" \
  "$runtime_temp_dir/mismatch.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$mismatch_database" \
    api-bootstrap
if [[ "$(bootstrap_fingerprint "$mismatch_database")" != "$mismatch_before" ]]; then
  echo "mismatched membership state가 자동 repair됐습니다." >&2
  exit 1
fi

run_bootstrap_success \
  "$extra_database" \
  "$runtime_temp_dir/valid.json" \
  "household-bootstrap: created" \
  "$runtime_temp_dir/extra-seed.log"
postgres_query "$extra_database" \
  "INSERT INTO users(email, display_name, status) VALUES ('extra@example.test', 'Extra', 'ACTIVE')" >/dev/null
extra_before="$(bootstrap_fingerprint "$extra_database")"
expect_failure \
  "extra state" \
  "$runtime_temp_dir/extra.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$extra_database" \
    api-bootstrap
if [[ "$(bootstrap_fingerprint "$extra_database")" != "$extra_before" ]]; then
  echo "extra bootstrap state가 자동 repair됐습니다." >&2
  exit 1
fi

printf '\n[bootstrap 9/12] profile and normal production fail-closed\n'
for invalid_profiles in \
  production,migration,bootstrap \
  bootstrap \
  production,bootstrap,local \
  production,bootstrap,test; do
  safe_profile_name="${invalid_profiles//,/-}"
  expect_failure \
    "invalid bootstrap profile $invalid_profiles" \
    "$runtime_temp_dir/profile-$safe_profile_name.log" \
    "$runtime_temp_dir/valid.json" \
    "${compose[@]}" run --rm -T --no-deps \
      --env "SPRING_PROFILES_ACTIVE=$invalid_profiles" \
      api-bootstrap
done
expect_failure \
  "normal production bootstrap override" \
  "$runtime_temp_dir/normal-bootstrap-override.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps \
    --env OUR_LEDGER_BOOTSTRAP_ENABLED=true \
    api

printf '\n[bootstrap 10/12] schema and database failure boundaries\n'
damaged_database=our_ledger_bootstrap_damaged
create_database "$damaged_database"
run_candidate_migration "$damaged_database" "$runtime_temp_dir/migration-damaged.log"
postgres_query "$damaged_database" "ALTER TABLE users DROP COLUMN status" >/dev/null
expect_failure \
  "JPA schema mismatch" \
  "$runtime_temp_dir/schema-mismatch.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/$damaged_database" \
    api-bootstrap
expect_failure \
  "unreachable bootstrap database" \
  "$runtime_temp_dir/database-unreachable.log" \
  "$runtime_temp_dir/valid.json" \
  "${compose[@]}" run --rm -T --no-deps \
    --env "SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:1/$POSTGRES_DB" \
    api-bootstrap

printf '\n[bootstrap 11/12] normal API startup without bootstrap replay\n'
normal_before="$(bootstrap_fingerprint "$POSTGRES_DB")"
normal_schema_before="$(schema_fingerprint "$POSTGRES_DB")"
"${compose[@]}" up --detach --wait --wait-timeout 240 api
if [[ "$(bootstrap_fingerprint "$POSTGRES_DB")" != "$normal_before" ]]; then
  echo "normal production API startup이 bootstrap state를 변경했습니다." >&2
  exit 1
fi
if [[ "$(schema_fingerprint "$POSTGRES_DB")" != "$normal_schema_before" ]]; then
  echo "normal production API startup이 Flyway history를 변경했습니다." >&2
  exit 1
fi

printf '\n[bootstrap 12/12] privacy, migration bytes, and residue precheck\n'
while IFS= read -r -d '' log_path; do
  assert_log_safe "$log_path"
done < <(find "$runtime_temp_dir" -type f -name '*.log' -print0)
"$ROOT_DIR/scripts/check-migrations.sh"
if [[ -n "$(docker ps --all --quiet \
  --filter "label=com.docker.compose.project=$project_name" \
  --filter "label=com.docker.compose.service=api-bootstrap")" ]]; then
  echo "bootstrap one-shot container residue가 남았습니다." >&2
  exit 1
fi

echo "Production Household bootstrap one-shot 검증을 통과했습니다."
