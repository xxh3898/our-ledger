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

echo "Docker Compose 검증을 통과했습니다."
