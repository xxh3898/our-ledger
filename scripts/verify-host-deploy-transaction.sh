#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  scripts/host_tools/test_deploy_transaction.py

bash -n "$ROOT_DIR/scripts/deploy-production.sh"

if grep -R -n -E -- \
  '--(root|app-root|app-dir|compose-file|state-dir|image|reporter|skip-lock|skip-backup|skip-migration)' \
  "$ROOT_DIR/scripts/deploy-production.sh" \
  "$ROOT_DIR/scripts/host_tools/production_host.py"; then
  printf 'Production deploy entrypoint에 caller override가 있습니다.\n' >&2
  exit 1
fi

if grep -R -n -E -- \
  'shell=True|down[[:space:]]+--volumes|docker[[:space:]]+(system|volume)[[:space:]]+prune' \
  "$ROOT_DIR/scripts/host_tools/deploy_transaction.py" \
  "$ROOT_DIR/scripts/host_tools/production_deploy.py"; then
  printf 'Deployment transaction에 금지된 command 경계가 있습니다.\n' >&2
  exit 1
fi

printf 'Restricted host deployment transaction 검증을 통과했습니다.\n'
