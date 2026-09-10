"""CI 전용 Docker layer cache 정책과 원래 build로의 fallback. 표준 라이브러리만 사용한다."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
MODES = {"disabled", "gha-read", "gha-write"}
DOCKERFILES = {
    "api": "infra/docker/api.Dockerfile",
    "web": "infra/docker/web.Dockerfile",
}
READERS = {
    "api": {"test-images"},
    "web": {"test-images"},
}
WRITERS = {"api": "test-images", "web": "test-images"}


def event_mode(environment: Mapping[str, str]) -> str:
    """직접 dev Full CI만 허용한다. reusable github context는 caller를 가리킨다."""
    if environment.get("GITHUB_ACTIONS") != "true" or environment.get("GITHUB_REPOSITORY") != "xxh3898/our-ledger":
        return "disabled"
    ref = environment.get("GITHUB_REF", "")
    if environment.get("GITHUB_WORKFLOW_REF") != f"xxh3898/our-ledger/.github/workflows/full-ci.yml@{ref}":
        return "disabled"
    if environment.get("GITHUB_EVENT_NAME") == "pull_request" and environment.get("GITHUB_BASE_REF") == "dev":
        return "gha-read" if re.fullmatch(r"refs/pull/[1-9][0-9]*/merge", ref) else "disabled"
    if environment.get("GITHUB_EVENT_NAME") == "push" and ref == "refs/heads/dev":
        return "gha-write"
    return "disabled"


def build_mode(family: str, environment: Mapping[str, str]) -> str:
    requested = environment.get("CI_DOCKER_CACHE_MODE", "disabled")
    if requested not in MODES:
        raise ValueError("unknown CI Docker cache mode")
    if family not in DOCKERFILES:
        raise ValueError("unknown CI Docker image family")
    allowed = event_mode(environment)
    job = environment.get("GITHUB_JOB", "")
    if requested == "disabled" or allowed == "disabled" or job not in READERS[family]:
        return "disabled"
    if requested == allowed == "gha-write" and job == WRITERS[family]:
        return "gha-write"
    return "gha-read"


def dependency_inputs(family: str, root: Path) -> list[Path]:
    dockerfile = root / DOCKERFILES[family]
    specific_ignore = Path(str(dockerfile) + ".dockerignore")
    # Dockerfile별 ignore가 root ignore보다 우선하는 실제 Docker context 계약.
    inputs = [dockerfile, specific_ignore if specific_ignore.exists() else root / ".dockerignore"]
    if family == "api":
        inputs += [root / "backend" / name for name in (
            "build.gradle.kts", "settings.gradle.kts", "gradle.properties", "gradlew",
        )]
        inputs += sorted(path for path in (root / "backend/gradle").rglob("*") if path.is_file())
    elif family == "web":
        inputs += [root / "frontend/package.json", root / "frontend/package-lock.json"]
    return sorted(inputs)


def cache_scope(family: str, platform: str, root: Path = ROOT) -> str:
    if family not in DOCKERFILES or platform not in {"linux/amd64", "linux/arm64"}:
        raise ValueError("unsupported CI cache identity")
    digest = hashlib.sha256()
    for path in dependency_inputs(family, root):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("invalid CI cache generation input")
        payload = path.read_bytes()
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(str(len(payload)).encode() + b"\0" + payload + b"\0")
    return f"our-ledger-ci-v1-{family}-{platform.replace('/', '-')}-dev-{digest.hexdigest()[:24]}"


def validate_arguments(family: str, arguments: list[str], root: Path) -> str | None:
    """기존 verifier option만 받으며 다른 context, 출력/credential/cache option을 금지한다."""
    if family not in DOCKERFILES or not arguments or Path(arguments[-1]).resolve() != root.resolve():
        raise ValueError("CI cache requires the canonical repository context")
    options: dict[str, list[str]] = {}
    index = 0
    while index < len(arguments) - 1:
        option = arguments[index]
        if option in {"--no-cache", "--pull"}:
            index += 1
            continue
        if option not in {"--file", "--tag", "--label", "--network", "--platform", "--progress"}:
            raise ValueError("unsupported CI image build option")
        if index + 1 >= len(arguments) - 1:
            raise ValueError("missing CI image build option value")
        value = arguments[index + 1]
        if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("invalid CI image build option value")
        options.setdefault(option, []).append(value)
        index += 2
    if len(options.get("--file", [])) != 1 or Path(options["--file"][0]).resolve() != (root / DOCKERFILES[family]).resolve():
        raise ValueError("CI cache requires the canonical family Dockerfile")
    if len(options.get("--tag", [])) != 1:
        raise ValueError("CI image build requires one local image tag")
    platforms = options.get("--platform", [])
    if len(platforms) > 1 or (platforms and platforms[0] not in {"linux/amd64", "linux/arm64"}):
        raise ValueError("unsupported CI image platform")
    return platforms[0] if platforms else None


def runtime_available(environment: Mapping[str, str]) -> bool:
    return (
        environment.get("CI_DOCKER_CACHE_READY") == "true"
        and bool(environment.get("ACTIONS_RUNTIME_TOKEN"))
        and environment.get("ACTIONS_RESULTS_URL", "").startswith("https://")
        and all(not any(ord(character) < 32 or ord(character) == 127 for character in environment.get(key, ""))
                for key in ("ACTIONS_RUNTIME_TOKEN", "ACTIONS_RESULTS_URL"))
    )


def cached_command(arguments: list[str], mode: str, scope: str, platform: str) -> list[str]:
    # --pull은 유지한다. 명시적인 dev cache 경로에서만 --no-cache를 제외한다.
    options = [argument for argument in arguments[:-1] if argument != "--no-cache"]
    if "--platform" not in options:
        options += ["--platform", platform]
    command = ["docker", "buildx", "build", "--load", *options,
               "--cache-from", f"type=gha,version=2,scope={scope},timeout=60s"]
    if mode == "gha-write":
        command += ["--cache-to", f"type=gha,version=2,scope={scope},mode=max,ignore-error=true,timeout=60s"]
    return [*command, arguments[-1]]


def clean_build(arguments: list[str], environment: Mapping[str, str], *, fallback: bool) -> int:
    options = list(arguments)
    if fallback and "--no-cache" not in options:
        options.insert(0, "--no-cache")
    clean_environment = {key: value for key, value in environment.items()
                         if key not in {"ACTIONS_RUNTIME_TOKEN", "ACTIONS_RESULTS_URL"}}
    return subprocess.run(["docker", "build", *options], env=clean_environment, check=False).returncode


def build_image(family: str, arguments: list[str], environment: Mapping[str, str], root: Path = ROOT) -> int:
    mode = build_mode(family, environment)
    platform = validate_arguments(family, arguments, root)
    if mode == "disabled":
        return clean_build(arguments, environment, fallback=False)
    if not runtime_available(environment):
        print("CI Docker cache 준비 불가: no-cache build로 검증합니다.", flush=True)
        return clean_build(arguments, environment, fallback=True)
    try:
        if platform is None:
            platform = environment.get("DOCKER_DEFAULT_PLATFORM") or subprocess.run(
                ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                env=dict(environment), check=True, capture_output=True, text=True, timeout=15,
            ).stdout.strip()
        scope = cache_scope(family, platform, root)
        print(f"CI Docker cache: mode={mode} scope={scope}", flush=True)
        result = subprocess.run(cached_command(arguments, mode, scope, platform), env=dict(environment), check=False)
        if result.returncode == 0:
            return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        # 도구 오류에 포함될 수 있는 credential/endpoint를 출력하지 않는다.
        pass
    print("CI Docker cache build 실패: no-cache build로 다시 검증합니다.", flush=True)
    return clean_build(arguments, environment, fallback=True)


def main() -> int:
    if sys.argv[1:] == ["policy"]:
        mode = event_mode(os.environ)
        print(f"mode={mode}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write(f"mode={mode}\n")
        return 0
    if len(sys.argv) > 3 and sys.argv[1] == "build":
        try:
            return build_image(sys.argv[2], sys.argv[3:], os.environ)
        except (OSError, ValueError, subprocess.SubprocessError):
            print("CI Docker image build 입력 또는 실행이 유효하지 않습니다.", file=sys.stderr)
            return 1
    print("Usage: docker_cache.py policy | build <api|web> <docker build options>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
