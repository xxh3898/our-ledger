#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_paths=(
  "README.md"
  "AGENTS.md"
  ".env.example"
  ".env.production.example"
  "compose.dev.yaml"
  "compose.prod.yaml"
  "compose.verify.yaml"
  "backend/build.gradle.kts"
  "backend/gradlew"
  "backend/src/main/resources/db/migration/V1__foundation.sql"
  "frontend/package.json"
  "frontend/package-lock.json"
  "infra/docker/api.Dockerfile"
  "infra/docker/HttpHealthCheck.java"
  "infra/docker/HttpFetch.java"
  "infra/docker/web.Dockerfile"
  "infra/nginx/nginx.conf"
  "docs/README.md"
  ".github/PULL_REQUEST_TEMPLATE.md"
  ".github/ISSUE_TEMPLATE/bug.yml"
  ".github/ISSUE_TEMPLATE/config.yml"
  ".github/ISSUE_TEMPLATE/decision.yml"
  ".github/ISSUE_TEMPLATE/feature.yml"
  ".github/workflows/deploy.yml"
  "runtime-manifest.json"
  "runtime-config.Dockerfile"
  "scripts/detect-runtime-config-change.sh"
  "scripts/release_tools/release_contract.py"
  "scripts/release_tools/test_release_contract.py"
  "scripts/verify-release-transport.sh"
  "scripts/verify.sh"
  "scripts/backup-production.sh"
  "scripts/bootstrap-production.sh"
  "scripts/offsite-backup-production.sh"
  "scripts/backup_tools/backup_artifact.py"
  "scripts/backup_tools/backup_core.sh"
  "scripts/backup_tools/offsite_backup.py"
  "scripts/backup_tools/check_fixture_state.py"
  "scripts/backup_tools/fixture.sql"
  "scripts/backup_tools/integrity-check.sql"
  "scripts/backup_tools/state-fingerprint.sql"
  "scripts/backup_tools/test_backup_artifact.py"
  "scripts/backup_tools/test_offsite_backup.py"
  "scripts/deploy-production.sh"
  "scripts/host_tools/deploy_transaction.py"
  "scripts/host_tools/fresh_bootstrap_state.py"
  "scripts/host_tools/fresh_host_bootstrap.py"
  "scripts/host_tools/host_state.py"
  "scripts/host_tools/production_deploy.py"
  "scripts/host_tools/production_fresh_bootstrap.py"
  "scripts/host_tools/production_host.py"
  "scripts/host_tools/synthetic_fresh_bootstrap.py"
  "scripts/host_tools/test_fresh_host_bootstrap.py"
  "scripts/host_tools/synthetic_host.py"
  "scripts/host_tools/test_deploy_transaction.py"
  "scripts/host_tools/test_host_state.py"
  "scripts/host_tools/test_runtime_config_evolution.py"
  "scripts/production-status.sh"
  "scripts/monitor-production.sh"
  "scripts/status_tools/production_status.py"
  "scripts/status_tools/monitor_policy.py"
  "scripts/status_tools/monitor_worker.py"
  "scripts/status_tools/test_production_status.py"
  "scripts/status_tools/test_monitor_policy.py"
  "scripts/verify-backup-restore.sh"
  "scripts/verify-host-deploy-transaction.sh"
  "scripts/verify-fresh-host-bootstrap.sh"
  "scripts/verify-host-state.sh"
  "scripts/verify-monitor-policy.sh"
  "scripts/verify-observability.sh"
  "scripts/verify-offsite-backup.sh"
  "scripts/verify-production-runtime.sh"
  "scripts/verify-production-bootstrap.sh"
  "scripts/verify-runtime-config-evolution.sh"
  "launchd/com.homeserver.our-ledger-monitor.plist.example"
  "launchd/com.homeserver.our-ledger-backup.plist.example"
  "launchd/com.homeserver.our-ledger-offsite.plist.example"
)

for path in "${required_paths[@]}"; do
  if [[ ! -e "$ROOT_DIR/$path" ]]; then
    echo "필수 경로가 없습니다: $path" >&2
    exit 1
  fi
done

issue_form_paths=(
  ".github/ISSUE_TEMPLATE/bug.yml"
  ".github/ISSUE_TEMPLATE/feature.yml"
  ".github/ISSUE_TEMPLATE/decision.yml"
)

for path in "${issue_form_paths[@]}"; do
  description_count="$(
    awk '/^description:[[:space:]]*[^[:space:]]/ { count++ } END { print count + 0 }' \
      "$ROOT_DIR/$path"
  )"
  about_count="$(
    awk '/^about:/ { count++ } END { print count + 0 }' "$ROOT_DIR/$path"
  )"
  if [[ "$description_count" -ne 1 || "$about_count" -ne 0 ]]; then
    echo "GitHub Issue Form 최상위 schema가 잘못됐습니다: $path" >&2
    exit 1
  fi
done

for script in "$ROOT_DIR"/scripts/*.sh; do
  bash -n "$script"
  if [[ ! -x "$script" ]]; then
    echo "실행 권한이 없는 shell script입니다: ${script#$ROOT_DIR/}" >&2
    exit 1
  fi
done

forbidden_names=(".env" "id_rsa" "id_ed25519")
for name in "${forbidden_names[@]}"; do
  if find "$ROOT_DIR" -path "$ROOT_DIR/.git" -prune -o -name "$name" -print | grep -q .; then
    echo "커밋 금지 파일이 발견됐습니다: $name" >&2
    exit 1
  fi
done

if find "$ROOT_DIR" -path "$ROOT_DIR/.git" -prune -o \( -name '*.pem' -o -name '*.key' -o -name '*.p12' -o -name '*.jks' \) -print | grep -q .; then
  echo "private key 또는 keystore 후보가 발견됐습니다." >&2
  exit 1
fi

if command -v git >/dev/null 2>&1 && git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT_DIR" diff --check
fi

echo "저장소 구조 검사를 통과했습니다."
