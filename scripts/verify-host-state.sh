#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  scripts/host_tools/test_host_state.py

bash -n \
  "$ROOT_DIR/scripts/backup-production.sh" \
  "$ROOT_DIR/scripts/bootstrap-production.sh" \
  "$ROOT_DIR/scripts/backup_tools/backup_core.sh"

if [[ ! -x "$ROOT_DIR/scripts/backup-production.sh" ]]; then
  printf 'Public backup wrapper에 실행 권한이 없습니다.\n' >&2
  exit 1
fi
if [[ ! -x "$ROOT_DIR/scripts/bootstrap-production.sh" ]]; then
  printf 'Fresh bootstrap wrapper에 실행 권한이 없습니다.\n' >&2
  exit 1
fi
if [[ -x "$ROOT_DIR/scripts/backup_tools/backup_core.sh" ]]; then
  printf 'Internal backup core는 직접 실행 가능하면 안 됩니다.\n' >&2
  exit 1
fi

if grep -Eq -- '--(root|app-root|app-dir|state-dir|compose-file)|OUR_LEDGER_.*ROOT' \
  "$ROOT_DIR/scripts/host_tools/production_host.py"; then
  printf 'Production host worker에 arbitrary host root override가 있습니다.\n' >&2
  exit 1
fi
if grep -R -n -E -- '--skip-lock|OUR_LEDGER_.*SKIP.*LOCK' \
  "$ROOT_DIR/scripts/backup-production.sh" \
  "$ROOT_DIR/scripts/backup_tools" \
  "$ROOT_DIR/scripts/host_tools"; then
  printf 'Public operation lock bypass가 발견됐습니다.\n' >&2
  exit 1
fi

printf 'Host state/shared operation lock 검증을 통과했습니다.\n'
