#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

if [[ ! -f "$BACKEND_DIR/build.gradle" && ! -f "$BACKEND_DIR/build.gradle.kts" ]]; then
  echo "Backend가 아직 bootstrap되지 않아 검증을 건너뜁니다."
  exit 0
fi

if [[ ! -x "$BACKEND_DIR/gradlew" ]]; then
  echo "Gradle build 파일은 있지만 실행 가능한 backend/gradlew가 없습니다." >&2
  exit 1
fi

(
  cd "$BACKEND_DIR"
  ./gradlew --no-daemon clean check
)

echo "Backend 검증을 통과했습니다."
