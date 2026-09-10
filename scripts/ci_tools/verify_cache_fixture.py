"""수동 전용: 승인된 빈 disposable Buildx builder 2개로 외부 cache 재사용을 검증한다.

check-repo/verify.sh에서는 실행하지 않는다. builder 생성·receipt 등록·삭제는 호출자 소유다.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER_TASKS = {"cold": "issue-123-cache-fixture-cold", "warm": "issue-123-cache-fixture-warm"}
BUILDERS = {phase: f"dev-our-ledger-{task}" for phase, task in BUILDER_TASKS.items()}


def run(arguments: list[str]) -> subprocess.CompletedProcess:
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"ACTIONS_RUNTIME_TOKEN", "ACTIONS_RESULTS_URL", "GITHUB_TOKEN", "GH_TOKEN"}}
    return subprocess.run(arguments, env=environment, check=True, capture_output=True, text=True, timeout=60)


def validate_builders(cold: str, warm: str) -> None:
    if (cold, warm) != (BUILDERS["cold"], BUILDERS["warm"]):
        raise ValueError("cleanup receipt 계약의 exact cold/warm builder 이름이 필요합니다")
    for name in (cold, warm):
        inspection = run(["docker", "buildx", "inspect", name]).stdout
        if not re.search(r"^Driver:\s+docker-container\s*$", inspection, re.M) or not re.search(r"^Status:\s+running\s*$", inspection, re.M):
            raise ValueError("사전에 승인·준비된 running docker-container builder가 필요합니다")
        if run(["docker", "buildx", "du", "--builder", name, "--format", "{{.ID}}"]).stdout.strip():
            raise ValueError("cold/warm 외부 cache 증명을 위해 두 builder 모두 비어 있어야 합니다")


def verify(cold: str, warm: str) -> None:
    validate_builders(cold, warm)
    revision = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("exact source SHA가 필요합니다")
    with tempfile.TemporaryDirectory(prefix="our-ledger-ci-cache-fixture-") as temporary:
        root = Path(temporary)
        context = root / "context"
        context.mkdir()
        (context / "Dockerfile").write_text("FROM scratch\nCOPY payload.txt /payload.txt\n", encoding="utf-8")
        payload = context / "payload.txt"
        payload.write_bytes(b"our-ledger cache fixture A\n")
        store = root / "cache"
        common = ["--platform", "linux/arm64", "--network", "none", "--progress", "plain"]
        for key, value in {"environment": "development", "project": "our-ledger",
                           "lifecycle": "task", "retain": "false", "git-head": revision}.items():
            common += ["--label", f"io.homeserver.cleanup.{key}={value}"]
        hashes = []
        for phase, builder in (("cold", cold), ("warm", warm), ("source-change", warm)):
            if phase == "source-change":
                payload.write_bytes(b"our-ledger cache fixture B\n")
            output = root / phase
            task = BUILDER_TASKS["cold" if phase == "cold" else "warm"]
            command = ["docker", "buildx", "build", "--builder", builder, *common,
                       "--label", f"io.homeserver.cleanup.task={task}",
                       "--output", f"type=local,dest={output}"]
            if phase == "cold":
                command += ["--no-cache", "--cache-to", f"type=local,dest={store},mode=max"]
            else:
                command += ["--cache-from", f"type=local,src={store}"]
            started = time.monotonic()
            result = run([*command, str(context)])
            elapsed = time.monotonic() - started
            log = result.stdout + result.stderr
            if phase == "warm" and not re.search(r"\bCACHED\b", log):
                raise ValueError("빈 warm builder가 외부 cache를 재사용했다는 log가 없습니다")
            actual = (output / "payload.txt").read_bytes()
            if actual != payload.read_bytes():
                raise ValueError("cache build output이 현재 source와 다릅니다")
            hashes.append(hashlib.sha256(actual).hexdigest())
            print(f"{phase}: PASS duration_seconds={elapsed:.3f} payload_sha256={hashes[-1]}")
        if hashes[0] != hashes[1] or hashes[1] == hashes[2]:
            raise ValueError("cold/warm equality 또는 source invalidation이 다릅니다")
    print("로컬 fixture PASS. GHA auth/backend와 실제 API/Web Hosted acceptance는 별도입니다.")
    print("임시 context/cache/output은 제거했습니다. 호출자 소유의 두 builder/cache는 승인된 cleanup 절차로 정리해야 합니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cold-builder", required=True)
    parser.add_argument("--warm-builder", required=True)
    args = parser.parse_args()
    try:
        verify(args.cold_builder, args.warm_builder)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Cache fixture 실패: builder 준비 상태 또는 cold/warm/source output 증거를 확인하세요.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
