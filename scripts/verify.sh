#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/15] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/15] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/15] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/15] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/15] Host state/shared operation lock 검사\n'
"$ROOT_DIR/scripts/verify-host-state.sh"

printf '\n[6/15] Host deployment transaction 검사\n'
"$ROOT_DIR/scripts/verify-host-deploy-transaction.sh"

printf '\n[7/15] Fresh-host bootstrap transaction 검사\n'
"$ROOT_DIR/scripts/verify-fresh-host-bootstrap.sh"

printf '\n[8/15] Release/Deploy source 검사\n'
"$ROOT_DIR/scripts/verify-release-transport.sh"

printf '\n[9/15] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[10/15] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[11/15] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[12/15] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[13/15] Production Household bootstrap 검사\n'
"$ROOT_DIR/scripts/verify-production-bootstrap.sh"

printf '\n[14/15] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n[15/15] Monitor policy/HomeOps 검사\n'
"$ROOT_DIR/scripts/verify-monitor-policy.sh"

printf '\n전체 검증을 통과했습니다.\n'
