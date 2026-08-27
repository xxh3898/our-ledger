#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Frontend package.json이 없습니다." >&2
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package-lock.json" ]]; then
  echo "Frontend package-lock.json이 없습니다." >&2
  exit 1
fi

node_major=""
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  if ! node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null)"; then
    node_major=""
  fi
fi

if [[ "$node_major" == "24" ]]; then
  (
    cd "$FRONTEND_DIR"
    npm ci
    npm run lint
    npm run typecheck
    npm run test:run
    npm run build
  )
else
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Node.js 24가 없고 Docker Compose fallback도 사용할 수 없습니다." >&2
    exit 1
  fi

  VERIFY_COMPOSE_FILE="$ROOT_DIR/compose.verify.yaml"
  cleanup() {
    docker compose -f "$VERIFY_COMPOSE_FILE" down --remove-orphans
  }
  trap cleanup EXIT INT TERM

  docker compose -f "$VERIFY_COMPOSE_FILE" run --rm --no-deps frontend

  trap - EXIT INT TERM
  cleanup
fi

echo "Frontend 검증을 통과했습니다."
