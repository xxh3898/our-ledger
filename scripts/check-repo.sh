#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_paths=(
  "README.md"
  "AGENTS.md"
  ".env.example"
  "compose.dev.yaml"
  "compose.verify.yaml"
  "backend/build.gradle.kts"
  "backend/gradlew"
  "backend/src/main/resources/db/migration/V1__foundation.sql"
  "frontend/package.json"
  "frontend/package-lock.json"
  "docs/README.md"
  ".github/PULL_REQUEST_TEMPLATE.md"
  ".github/ISSUE_TEMPLATE/feature.yml"
  "scripts/verify.sh"
)

for path in "${required_paths[@]}"; do
  if [[ ! -e "$ROOT_DIR/$path" ]]; then
    echo "필수 경로가 없습니다: $path" >&2
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
