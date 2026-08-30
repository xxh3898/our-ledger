#!/usr/bin/env bash
set -euo pipefail

readonly ZERO_SHA=0000000000000000000000000000000000000000

if [[ "$#" -ne 3 ]]; then
  printf 'Usage: detect-runtime-config-change.sh <before-sha> <after-sha> <force-sync>\n' >&2
  exit 64
fi

before_sha="$1"
after_sha="$2"
force_sync="$3"

if [[ ! "$before_sha" =~ ^[0-9a-f]{40}$ ]] \
  || [[ ! "$after_sha" =~ ^[0-9a-f]{40}$ ]] \
  || [[ "$after_sha" == "$ZERO_SHA" ]]; then
  printf 'Git revisions must be exact lowercase nonzero candidate SHAs\n' >&2
  exit 64
fi
if [[ "$force_sync" != true && "$force_sync" != false ]]; then
  printf 'force-sync must be true or false\n' >&2
  exit 64
fi
if ! git cat-file -e "${after_sha}^{commit}" 2>/dev/null; then
  printf 'Candidate revision is unavailable\n' >&2
  exit 64
fi

if [[ "$before_sha" == "$ZERO_SHA" ]]; then
  printf 'update\n'
  exit 0
fi
if ! git cat-file -e "${before_sha}^{commit}" 2>/dev/null; then
  printf 'Previous production revision is unavailable\n' >&2
  exit 64
fi
if ! git merge-base --is-ancestor "$before_sha" "$after_sha"; then
  printf 'Production revision range is invalid\n' >&2
  exit 64
fi
if [[ "$force_sync" == true ]]; then
  printf 'update\n'
  exit 0
fi

if git diff --quiet \
  "$before_sha" \
  "$after_sha" \
  -- \
  compose.prod.yaml \
  infra/nginx/nginx.conf \
  runtime-config.Dockerfile \
  scripts/backup-production.sh \
  scripts/backup_tools/backup_artifact.py \
  scripts/backup_tools/backup_core.sh \
  scripts/deploy-production.sh \
  scripts/host_tools/deploy_transaction.py \
  scripts/host_tools/host_state.py \
  scripts/host_tools/production_deploy.py \
  scripts/host_tools/production_host.py \
  scripts/monitor-production.sh \
  scripts/production-status.sh \
  scripts/release_tools/release_contract.py \
  scripts/status_tools/monitor_policy.py \
  scripts/status_tools/monitor_worker.py \
  scripts/status_tools/production_status.py
then
  printf 'keep\n'
else
  diff_status="$?"
  if [[ "$diff_status" -eq 1 ]]; then
    printf 'update\n'
    exit 0
  fi
  printf 'Runtime config diff failed\n' >&2
  exit "$diff_status"
fi
