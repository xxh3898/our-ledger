#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$ROOT_DIR/docs"

while IFS= read -r -d '' file; do
  first_line="$(sed -n '1p' "$file")"
  if [[ "$first_line" != "---" ]]; then
    echo "문서 front matter가 없습니다: ${file#$ROOT_DIR/}" >&2
    exit 1
  fi

  for field in status version last_updated related; do
    if ! grep -q "^${field}:" "$file"; then
      echo "문서 메타데이터 '$field'가 없습니다: ${file#$ROOT_DIR/}" >&2
      exit 1
    fi
  done

done < <(find "$DOCS_DIR" -type f -name '*.md' -print0)

if grep -RInE '[[:blank:]]+$' "$DOCS_DIR" --include='*.md'; then
  echo "문서에 줄 끝 공백이 있습니다." >&2
  exit 1
fi

python3 "$ROOT_DIR/scripts/check_markdown_links.py" "$DOCS_DIR"

echo "문서 검사를 통과했습니다."
