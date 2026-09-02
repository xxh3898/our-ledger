#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

/bin/bash -n \
  "$ROOT_DIR/scripts/backup-our-ledger-bootstrap.sh" \
  "$ROOT_DIR/scripts/offsite-our-ledger-bootstrap.sh"

cd "$ROOT_DIR"
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  scripts.host_tools.test_fixed_bootstrap

printf 'Fixed backup/offsite bootstrap source 검증을 통과했습니다.\n'
