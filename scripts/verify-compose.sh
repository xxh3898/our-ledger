#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose를 사용할 수 없습니다." >&2
  exit 1
fi

docker compose \
  --env-file "$ROOT_DIR/.env.example" \
  -f "$ROOT_DIR/compose.dev.yaml" \
  --profile app \
  config --quiet

rendered_dev_config="$(
  docker compose \
    --env-file "$ROOT_DIR/.env.example" \
    -f "$ROOT_DIR/compose.dev.yaml" \
    --profile app \
    config --format json
)"

python3 -c '
import json
import sys

expected = {
    "OUR_LEDGER_BOOTSTRAP_ENABLED",
    "OUR_LEDGER_BOOTSTRAP_HOUSEHOLD_NAME",
    "OUR_LEDGER_BOOTSTRAP_OWNER_EMAIL",
    "OUR_LEDGER_BOOTSTRAP_OWNER_DISPLAY_NAME",
    "OUR_LEDGER_BOOTSTRAP_MEMBER_EMAIL",
    "OUR_LEDGER_BOOTSTRAP_MEMBER_DISPLAY_NAME",
}
config = json.load(sys.stdin)
services = config.get("services", {})
api_environment = set(services.get("api", {}).get("environment", {}))
postgres_environment = set(services.get("postgres", {}).get("environment", {}))

missing_from_api = sorted(expected - api_environment)
leaked_to_postgres = sorted(expected & postgres_environment)
if missing_from_api:
    print(
        "api service에 bootstrap 환경변수가 없습니다: " + ", ".join(missing_from_api),
        file=sys.stderr,
    )
if leaked_to_postgres:
    print(
        "postgres service에 bootstrap 환경변수가 잘못 전달됩니다: "
        + ", ".join(leaked_to_postgres),
        file=sys.stderr,
    )
if missing_from_api or leaked_to_postgres:
    raise SystemExit(1)
' <<< "$rendered_dev_config"

docker compose \
  -f "$ROOT_DIR/compose.verify.yaml" \
  config --quiet

required_production_environment=(
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

without_production_environment=(env)
for variable_name in "${required_production_environment[@]}"; do
  without_production_environment+=("-u" "$variable_name")
done

if "${without_production_environment[@]}" \
  docker compose \
  --env-file /dev/null \
  -f "$ROOT_DIR/compose.prod.yaml" \
  config --quiet >/dev/null 2>&1; then
  echo "필수 환경변수 없이 production Compose가 render됐습니다." >&2
  exit 1
fi

docker compose \
  --env-file "$ROOT_DIR/.env.production.example" \
  -f "$ROOT_DIR/compose.prod.yaml" \
  config --quiet

docker compose \
  --env-file "$ROOT_DIR/.env.production.example" \
  -f "$ROOT_DIR/compose.prod.yaml" \
  --profile migration \
  --profile bootstrap \
  config --format json \
  | python3 "$ROOT_DIR/scripts/check-production-compose.py"

echo "Docker Compose 검증을 통과했습니다."
