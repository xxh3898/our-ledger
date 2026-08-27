#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/6] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/6] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/6] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/6] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/6] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[6/6] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n전체 검증을 통과했습니다.\n'
