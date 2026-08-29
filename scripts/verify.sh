#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/9] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/9] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/9] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/9] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/9] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[6/9] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[7/9] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[8/9] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[9/9] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n전체 검증을 통과했습니다.\n'
