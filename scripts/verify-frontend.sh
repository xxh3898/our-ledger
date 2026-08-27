#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Frontend가 아직 bootstrap되지 않아 검증을 건너뜁니다."
  exit 0
fi

run_if_present() {
  local manager="$1"
  local script="$2"
  case "$manager" in
    npm) npm run "$script" --if-present ;;
    pnpm) pnpm run --if-present "$script" ;;
    yarn) yarn run "$script" --if-present ;;
  esac
}

(
  cd "$FRONTEND_DIR"
  if [[ -f pnpm-lock.yaml ]]; then
    corepack enable
    pnpm install --frozen-lockfile
    manager=pnpm
  elif [[ -f yarn.lock ]]; then
    corepack enable
    yarn install --immutable
    manager=yarn
  elif [[ -f package-lock.json ]]; then
    npm ci
    manager=npm
  else
    echo "Frontend lockfile이 없습니다." >&2
    exit 1
  fi

  run_if_present "$manager" lint
  run_if_present "$manager" typecheck
  run_if_present "$manager" test:run
  run_if_present "$manager" build
)

echo "Frontend 검증을 통과했습니다."
