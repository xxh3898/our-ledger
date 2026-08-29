#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/11] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/11] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/11] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/11] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/11] Release/Deploy source 검사\n'
"$ROOT_DIR/scripts/verify-release-transport.sh"

printf '\n[6/11] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[7/11] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[8/11] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[9/11] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[10/11] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n[11/11] Monitor policy/HomeOps 검사\n'
"$ROOT_DIR/scripts/verify-monitor-policy.sh"

printf '\n전체 검증을 통과했습니다.\n'
