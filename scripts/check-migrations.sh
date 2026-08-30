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

python3 - "$MIGRATION_DIR" <<'PY'
import hashlib
from pathlib import Path
import sys

migration_dir = Path(sys.argv[1])
expected = {
    "V1__foundation.sql": "a262ed07340ddec85aec2e5080385c713f956746ed397cf76244b082d43168ea",
    "V2__users_households.sql": "a5e4ca2b9640cb3b8a71758c81bfdbe18b15283819d483493b87c92a3c98435c",
    "V3__accounts_categories_transactions.sql": "aecf464fd5eafd1bb5a4c14a4d866ff583cc7e57fdc15900291dddf8d97c5c75",
    "V4__transaction_account_entries.sql": "5af9d22ccb35614e1be0d0c81f0ed6191c249aff130836c5e6b10a3b07219edc",
    "V5__credit_card_liability_constraint.sql": "76a602f1696f58d0ceb018bd29139d1de23a8757e2c71a61b136d3b41080f9f4",
    "V6__budgets.sql": "4ed250062d50dfd8c69fd065d65704fade4972880889b57c18eff1328a522c4d",
    "V7__recurring_transactions.sql": "604a0cd0a102bc7aafbde540a74421d9bce6cded6ecac0f6f0316a10b70a0f75",
    "V8__goals.sql": "a24586f01f247b53321e82972da5fdb34f4329d9390f4bba293d4e11d6770083",
}
for filename, expected_digest in expected.items():
    path = migration_dir / filename
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"적용된 Flyway migration 파일이 없거나 regular file이 아닙니다: {filename}")
    actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise SystemExit(f"적용된 Flyway migration byte가 변경됐습니다: {filename}")
PY

echo "Flyway migration 파일 검사를 통과했습니다."
