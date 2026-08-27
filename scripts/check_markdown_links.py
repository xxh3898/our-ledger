#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    errors: list[str] = []

    for file in root.rglob("*.md"):
        text = file.read_text(encoding="utf-8")
        for raw in LINK.findall(text):
            target = raw.strip().split()[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = unquote(target.split("#", 1)[0])
            if not path_part:
                continue
            resolved = (file.parent / path_part).resolve()
            try:
                resolved.relative_to(root.parent)
            except ValueError:
                errors.append(f"{file}: 저장소 밖 링크: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{file}: 존재하지 않는 링크: {target}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Markdown 상대 링크 검사를 통과했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
