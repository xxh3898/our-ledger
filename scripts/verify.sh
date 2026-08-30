#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/13] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/13] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/13] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/13] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/13] Host state/shared operation lock 검사\n'
"$ROOT_DIR/scripts/verify-host-state.sh"

printf '\n[6/13] Host deployment transaction 검사\n'
"$ROOT_DIR/scripts/verify-host-deploy-transaction.sh"

printf '\n[7/13] Release/Deploy source 검사\n'
"$ROOT_DIR/scripts/verify-release-transport.sh"

printf '\n[8/13] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[9/13] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[10/13] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[11/13] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[12/13] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n[13/13] Monitor policy/HomeOps 검사\n'
"$ROOT_DIR/scripts/verify-monitor-policy.sh"

printf '\n전체 검증을 통과했습니다.\n'
