#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/8] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/8] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/8] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/8] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/8] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[6/8] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[7/8] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[8/8] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n전체 검증을 통과했습니다.\n'
