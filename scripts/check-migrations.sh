#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATION_DIR="$ROOT_DIR/backend/src/main/resources/db/migration"

if [[ ! -d "$MIGRATION_DIR" ]]; then
  echo "Flyway migration 디렉터리가 없습니다." >&2
  exit 1
fi

files=()
while IFS= read -r file; do
  files+=("$file")
done < <(find "$MIGRATION_DIR" -maxdepth 1 -type f -name 'V*.sql' | sort)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "Flyway migration 파일이 없습니다." >&2
  exit 1
fi

seen_versions="|"
for file in "${files[@]}"; do
  name="$(basename "$file")"
  if [[ ! "$name" =~ ^V([0-9]+([.][0-9]+)*)__[a-z0-9_]+[.]sql$ ]]; then
    echo "Flyway 파일명이 규칙과 다릅니다: $name" >&2
    exit 1
  fi
  version="${BASH_REMATCH[1]}"
  if [[ "$seen_versions" == *"|$version|"* ]]; then
    echo "중복 Flyway 버전입니다: $version" >&2
    exit 1
  fi
  seen_versions+="$version|"
done

echo "Flyway migration 파일 검사를 통과했습니다."
