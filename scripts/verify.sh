#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/10] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/10] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/10] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/10] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/10] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[6/10] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[7/10] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[8/10] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[9/10] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n[10/10] Monitor policy/HomeOps 검사\n'
"$ROOT_DIR/scripts/verify-monitor-policy.sh"

printf '\n전체 검증을 통과했습니다.\n'
