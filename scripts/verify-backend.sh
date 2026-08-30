#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

if [[ ! -f "$BACKEND_DIR/build.gradle" && ! -f "$BACKEND_DIR/build.gradle.kts" ]]; then
  echo "Backend build 파일이 없습니다." >&2
  exit 1
fi

if [[ ! -x "$BACKEND_DIR/gradlew" ]]; then
  echo "Gradle build 파일은 있지만 실행 가능한 backend/gradlew가 없습니다." >&2
  exit 1
fi

java_properties=""
java_major=""
if command -v java >/dev/null 2>&1; then
  if java_properties="$(java -XshowSettings:properties -version 2>&1)"; then
    java_major="$(awk -F'= ' '/java.version =/{split($2, version, "."); print version[1]; exit}' <<< "$java_properties")"
  fi
fi

if [[ "$java_major" == "25" ]]; then
  (
    cd "$BACKEND_DIR"
    ./gradlew --no-daemon clean check
  )
else
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Java 25가 없고 Docker Compose fallback도 사용할 수 없습니다." >&2
    exit 1
  fi

  VERIFY_COMPOSE_FILE="$ROOT_DIR/compose.verify.yaml"
  cleanup() {
    docker compose -f "$VERIFY_COMPOSE_FILE" down --remove-orphans
  }
  trap cleanup EXIT INT TERM

  docker compose -f "$VERIFY_COMPOSE_FILE" up -d --wait postgres
  docker compose -f "$VERIFY_COMPOSE_FILE" run --rm --no-deps backend

  trap - EXIT INT TERM
  cleanup
fi

echo "Backend 검증을 통과했습니다."
