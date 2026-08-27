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

docker compose \
  -f "$ROOT_DIR/compose.verify.yaml" \
  config --quiet

echo "Docker Compose 검증을 통과했습니다."
