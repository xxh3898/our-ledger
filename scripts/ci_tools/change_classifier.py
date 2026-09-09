"""PR 변경 영향과 최종 CI 결과의 fail-safe 계약. Python 표준 라이브러리만 사용한다."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = "backend/src/main/java/io/github/xxh3898/ourledger/"
BACKEND_TEST_ROOT = "backend/src/test/java/io/github/xxh3898/ourledger/"
DOMAIN_PACKAGES = {
    "account", "assets", "budget", "calendar", "category", "export", "goal",
    "statistics", "transaction",
}
AUTHORITY_NAME = re.compile(
    r"Config|Security|Bootstrap|Migration|Profile|Scheduler|Operational|Health|"
    r"Authentication|Authorization|Csrf|Identity|Household|Filter|Guard|"
    r"Controller|Request|Response|Application", re.IGNORECASE,
)
HEAVY_JOBS = {
    "backup-docker-authority", "production-runtime", "production-bootstrap",
    "fresh-host-bootstrap", "host-state", "fixed-bootstrap",
    "runtime-config-evolution", "host-deploy-transaction", "backup-restore",
    "offsite-backup", "observability", "monitor-policy", "release-transport",
}
ALL_JOBS = {"repository", "backend", "frontend", *HEAVY_JOBS}
FULL_CATEGORIES = {"ops-runtime", "mixed/unknown"}
FLAGS = ("run_backend", "run_frontend", "run_full")


def plan(category: str, reason: str) -> dict[str, str]:
    full = category in FULL_CATEGORIES
    return {
        "category": category,
        "reason": reason,
        "run_backend": str(full or category == "backend-only").lower(),
        "run_frontend": str(full or category == "frontend-only").lower(),
        "run_full": str(full).lower(),
    }


def full(reason: str) -> dict[str, str]:
    return plan("mixed/unknown", reason)


def path_category(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        return "unknown"
    # 실행·배포·보안 및 API/DB 계약은 Markdown 여부보다 먼저 분류한다.
    if path.startswith((
        "infra/", "scripts/", ".github/", "launchd/", "backend/src/main/resources/",
        "backend/src/test/resources/", "docs/03-data/", "docs/04-api/",
        "docs/06-security/", "docs/08-operations/", "docs/09-decisions/",
    )) or path in {"AGENTS.md", "runtime-manifest.json", "runtime-config.Dockerfile"}:
        return "ops-runtime"
    if path.startswith(("compose.", ".env", ".dockerignore")):
        return "ops-runtime"
    if path in {"README.md", "docs/README.md", "frontend/README.md", "backend/README.md"}:
        return "docs"
    if re.fullmatch(r"docs/(00-overview|01-product|02-domain|05-frontend|07-quality)/.+\.md", path):
        return "docs"
    if re.fullmatch(r"frontend/src/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(ts|tsx|css)", path):
        return "frontend"
    if path.startswith("frontend/"):
        # package/lockfile, Vite/TS 설정, index/manifest, build script와 신규 asset 종류.
        return "ops-runtime"
    if path.startswith(BACKEND_ROOT):
        relative = path.removeprefix(BACKEND_ROOT)
        parts = relative.split("/")
        if (
            len(parts) == 2
            and parts[0] in DOMAIN_PACKAGES
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*\.java", parts[1])
            and not AUTHORITY_NAME.search(parts[1])
        ):
            return "backend"
        return "ops-runtime"
    if path.startswith(BACKEND_TEST_ROOT):
        filename = path.removeprefix(BACKEND_TEST_ROOT)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*Test\.java", filename) and not AUTHORITY_NAME.search(filename):
            return "backend"
        return "ops-runtime"
    if path.startswith("backend/"):
        return "ops-runtime"
    return "unknown"


def classify_paths(paths: list[str]) -> dict[str, str]:
    if not paths:
        return full("empty-diff")
    categories = {path_category(path) for path in paths}
    if "unknown" in categories:
        return full("unknown-path")
    if "ops-runtime" in categories:
        return plan("ops-runtime", "authority-or-runtime-path")
    categories.discard("docs")
    if not categories:
        return plan("docs-only", "documentation-only")
    if categories == {"frontend"}:
        return plan("frontend-only", "frontend-with-optional-docs")
    if categories == {"backend"}:
        return plan("backend-only", "backend-with-optional-docs")
    return full("mixed-source-paths")


def changed_paths(base_sha: str, head_sha: str, root: Path) -> list[str]:
    for revision in (base_sha, head_sha):
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision == "0" * 40:
            raise ValueError("invalid revision")
    # rename 감지를 끄고 이동 전 삭제와 이동 후 추가 경로를 모두 검증한다.
    result = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--raw",
         "--no-abbrev", "-z", f"{base_sha}...{head_sha}", "--"],
        cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if not result.stdout:
        return []
    records = result.stdout.decode("utf-8").split("\0")
    if records.pop() != "" or len(records) % 2:
        raise ValueError("invalid diff framing")
    paths = []
    for index in range(0, len(records), 2):
        match = re.fullmatch(
            r":(000000|100644) (000000|100644) [0-9a-f]{40} [0-9a-f]{40} ([AMD])",
            records[index],
        )
        if match is None:
            # symlink, gitlink, executable/type changes와 모르는 status는 Full이다.
            raise ValueError("unsupported diff entry")
        paths.append(records[index + 1])
    return paths


def classify_event(environment: Mapping[str, str], root: Path = ROOT) -> dict[str, str]:
    if environment.get("CI_EVENT_NAME") != "pull_request" or environment.get("CI_BASE_REF") != "dev":
        return full("full-event-or-target")
    repository = environment.get("CI_REPOSITORY", "")
    ref = environment.get("CI_REF", "")
    # reusable workflow의 github context는 caller 것이다. 다른 caller는 항상 Full이다.
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not re.fullmatch(r"refs/pull/[1-9][0-9]*/merge", ref)
        or environment.get("CI_WORKFLOW_REF") != f"{repository}/.github/workflows/full-ci.yml@{ref}"
    ):
        return full("reusable-or-unknown-workflow")
    try:
        paths = changed_paths(environment.get("CI_BASE_SHA", ""), environment.get("CI_HEAD_SHA", ""), root)
    except (OSError, ValueError, subprocess.SubprocessError):
        return full("diff-unavailable-or-unsupported")
    return classify_paths(paths)


def check_gate(needs: object) -> None:
    if not isinstance(needs, dict) or set(needs) != ALL_JOBS:
        raise ValueError("CI gate dependency set differs")
    if not all(isinstance(job, dict) for job in needs.values()):
        raise ValueError("CI gate dependency shape differs")
    repository = needs["repository"]
    if repository.get("result") != "success":
        raise ValueError("repository validation did not succeed")
    outputs = repository.get("outputs")
    if not isinstance(outputs, dict) or outputs.get("category") not in {
        "docs-only", "frontend-only", "backend-only", *FULL_CATEGORIES,
    }:
        raise ValueError("classifier category is unavailable")
    expected = plan(outputs["category"], "gate")
    if any(outputs.get(flag) != expected[flag] for flag in FLAGS):
        raise ValueError("classifier flags differ from category")
    for name, job in needs.items():
        if name == "repository":
            continue
        flag = {"backend": "run_backend", "frontend": "run_frontend"}.get(name, "run_full")
        expected_result = "success" if outputs[flag] == "true" else "skipped"
        if job.get("result") != expected_result:
            raise ValueError(f"{name} did not complete with expected {expected_result}")


def main() -> int:
    if sys.argv[1:] == ["classify"]:
        decision = classify_event(os.environ)
        output = "".join(f"{key}={value}\n" for key, value in decision.items())
        print(output, end="")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as destination:
                destination.write(output)
        return 0
    if sys.argv[1:] == ["gate"]:
        try:
            check_gate(json.loads(os.environ.get("CI_NEEDS_JSON", "null")))
        except (ValueError, TypeError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print("CI gate 검증을 통과했습니다.")
        return 0
    print("Usage: change_classifier.py classify|gate", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
