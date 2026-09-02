#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/18] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/18] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/18] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/18] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/18] Host state/shared operation lock 검사\n'
"$ROOT_DIR/scripts/verify-host-state.sh"

printf '\n[6/18] Host deployment transaction 검사\n'
"$ROOT_DIR/scripts/verify-host-deploy-transaction.sh"

printf '\n[7/18] Fresh-host bootstrap transaction 검사\n'
"$ROOT_DIR/scripts/verify-fresh-host-bootstrap.sh"

printf '\n[8/18] Runtime-config evolution bridge 검사\n'
"$ROOT_DIR/scripts/verify-runtime-config-evolution.sh"

printf '\n[9/18] Release/Deploy source 검사\n'
"$ROOT_DIR/scripts/verify-release-transport.sh"

printf '\n[10/18] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[11/18] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[12/18] Backup Docker executable authority 검사\n'
"$ROOT_DIR/scripts/verify-backup-docker-authority.sh"

printf '\n[13/18] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[14/18] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[15/18] Production Household bootstrap 검사\n'
"$ROOT_DIR/scripts/verify-production-bootstrap.sh"

printf '\n[16/18] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n[17/18] Monitor policy/HomeOps 검사\n'
"$ROOT_DIR/scripts/verify-monitor-policy.sh"

printf '\n[18/18] Encrypted offsite backup source 검사\n'
"$ROOT_DIR/scripts/verify-offsite-backup.sh"

printf '\n전체 검증을 통과했습니다.\n'
