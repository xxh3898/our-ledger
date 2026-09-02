#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n[1/19] 저장소 구조 검사\n'
"$ROOT_DIR/scripts/check-repo.sh"

printf '\n[2/19] 문서 검사\n'
"$ROOT_DIR/scripts/check-docs.sh"

printf '\n[3/19] Flyway migration 검사\n'
"$ROOT_DIR/scripts/check-migrations.sh"

printf '\n[4/19] Docker Compose 검사\n'
"$ROOT_DIR/scripts/verify-compose.sh"

printf '\n[5/19] Host state/shared operation lock 검사\n'
"$ROOT_DIR/scripts/verify-host-state.sh"

printf '\n[6/19] Host deployment transaction 검사\n'
"$ROOT_DIR/scripts/verify-host-deploy-transaction.sh"

printf '\n[7/19] Fresh-host bootstrap transaction 검사\n'
"$ROOT_DIR/scripts/verify-fresh-host-bootstrap.sh"

printf '\n[8/19] Fixed backup/offsite bootstrap source 검사\n'
"$ROOT_DIR/scripts/verify-fixed-bootstrap.sh"

printf '\n[9/19] Runtime-config evolution bridge 검사\n'
"$ROOT_DIR/scripts/verify-runtime-config-evolution.sh"

printf '\n[10/19] Release/Deploy source 검사\n'
"$ROOT_DIR/scripts/verify-release-transport.sh"

printf '\n[11/19] Backend 검사\n'
"$ROOT_DIR/scripts/verify-backend.sh"

printf '\n[12/19] Frontend 검사\n'
"$ROOT_DIR/scripts/verify-frontend.sh"

printf '\n[13/19] Backup Docker executable authority 검사\n'
"$ROOT_DIR/scripts/verify-backup-docker-authority.sh"

printf '\n[14/19] Backup/Restore 검사\n'
"$ROOT_DIR/scripts/verify-backup-restore.sh"

printf '\n[15/19] Production runtime 검사\n'
"$ROOT_DIR/scripts/verify-production-runtime.sh"

printf '\n[16/19] Production Household bootstrap 검사\n'
"$ROOT_DIR/scripts/verify-production-bootstrap.sh"

printf '\n[17/19] Observability/status 검사\n'
"$ROOT_DIR/scripts/verify-observability.sh"

printf '\n[18/19] Monitor policy/HomeOps 검사\n'
"$ROOT_DIR/scripts/verify-monitor-policy.sh"

printf '\n[19/19] Encrypted offsite backup source 검사\n'
"$ROOT_DIR/scripts/verify-offsite-backup.sh"

printf '\n전체 검증을 통과했습니다.\n'
