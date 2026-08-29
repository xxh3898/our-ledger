#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/7] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/7] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/7] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/7] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/7] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[6/7] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[7/7] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n전체 검증을 통과했습니다.\n'
