#!/usr/bin/env python3
"""Pure validation for the immutable release transport source contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ZERO_SHA = "0" * 40
ZERO_DIGEST = "sha256:" + ("0" * 64)
COMMAND_NAME = "deploy-our-ledger-v1"
BOOTSTRAP_COMMAND_NAME = "bootstrap-our-ledger-v1"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
ACTOR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
RUN_ID_PATTERN = re.compile(r"[1-9][0-9]{0,19}")
PUBLISH_REPOSITORY = "xxh3898/our-ledger"
VALIDATION_WORKFLOW_NAME = "Release Source Harness"
VALIDATION_WORKFLOW_PATH = ".github/workflows/deploy.yml"
VALIDATION_WORKFLOW_EVENTS = frozenset(("push", "workflow_dispatch"))
MAX_JSON_BYTES = 8 * 1024 * 1024
KEEP_COMMAND_PATTERN = re.compile(
    rf"{COMMAND_NAME} ([0-9a-f]{{40}}) keep ([A-Za-z0-9][A-Za-z0-9_-]{{0,63}})"
)
UPDATE_COMMAND_PATTERN = re.compile(
    rf"{COMMAND_NAME} ([0-9a-f]{{40}}) update (sha256:[0-9a-f]{{64}}) "
    r"([A-Za-z0-9][A-Za-z0-9_-]{0,63})"
)
BOOTSTRAP_COMMAND_PATTERN = re.compile(
    rf"{BOOTSTRAP_COMMAND_NAME} ([0-9a-f]{{40}}) (sha256:[0-9a-f]{{64}}) "
    r"([A-Za-z0-9][A-Za-z0-9_-]{0,63})"
)


class ContractError(ValueError):
    """Raised when release transport input violates the fixed contract."""


def validate_revision(value: str, *, allow_zero: bool = False) -> str:
    if SHA_PATTERN.fullmatch(value) is None:
        raise ContractError("release revision is invalid")
    if not allow_zero and value == ZERO_SHA:
        raise ContractError("release revision is invalid")
    return value


def validate_digest(value: str) -> str:
    if DIGEST_PATTERN.fullmatch(value) is None or value == ZERO_DIGEST:
        raise ContractError("release digest is invalid")
    return value


def validate_actor(value: str) -> str:
    if ACTOR_PATTERN.fullmatch(value) is None:
        raise ContractError("release actor is invalid")
    return value


def validate_run_id(value: str) -> int:
    if RUN_ID_PATTERN.fullmatch(value) is None:
        raise ContractError("validation run id is invalid")
    return int(value)


def validate_publish_request(
    *,
    revision: str,
    validation_run_id: str,
) -> dict[str, int | str]:
    return {
        "releaseSha": validate_revision(revision),
        "validationRunId": validate_run_id(validation_run_id),
    }


def validate_publish_authority(
    *,
    revision: str,
    validation_run_id: str,
    repository: str,
    run: object,
) -> dict[str, int | str]:
    request = validate_publish_request(
        revision=revision,
        validation_run_id=validation_run_id,
    )
    if repository != PUBLISH_REPOSITORY or type(run) is not dict:
        raise ContractError("publish authority is invalid")

    run_id = run.get("id")
    if type(run_id) is not int or run_id != request["validationRunId"]:
        raise ContractError("publish authority is invalid")
    for repository_key in ("repository", "head_repository"):
        run_repository = run.get(repository_key)
        if type(run_repository) is not dict:
            raise ContractError("publish authority is invalid")
        if run_repository.get("full_name") != repository:
            raise ContractError("publish authority is invalid")

    expected = {
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": request["releaseSha"],
        "name": VALIDATION_WORKFLOW_NAME,
        "path": VALIDATION_WORKFLOW_PATH,
        "status": "completed",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ContractError("publish authority is invalid")
    if run.get("event") not in VALIDATION_WORKFLOW_EVENTS:
        raise ContractError("publish authority is invalid")
    return request


def classify_package_tag(
    *,
    revision: str,
    digest: str,
    versions: object,
) -> str:
    revision = validate_revision(revision)
    digest = validate_digest(digest)
    entries = _flatten_package_versions(versions)

    candidate_count = 0
    tagged_digests: list[str] = []
    for entry in entries:
        version_digest = validate_digest(_required_string(entry, "name"))
        metadata = entry.get("metadata")
        if type(metadata) is not dict or metadata.get("package_type") != "container":
            raise ContractError("package metadata is invalid")
        container = metadata.get("container")
        if type(container) is not dict:
            raise ContractError("package metadata is invalid")
        tags = container.get("tags")
        if type(tags) is not list or any(type(tag) is not str or not tag for tag in tags):
            raise ContractError("package metadata is invalid")
        if len(tags) != len(set(tags)):
            raise ContractError("package metadata is invalid")

        if version_digest == digest:
            candidate_count += 1
        if revision in tags:
            tagged_digests.append(version_digest)

    if candidate_count != 1:
        raise ContractError("candidate package digest is unavailable")
    if not tagged_digests:
        return "create"
    if tagged_digests == [digest]:
        return "reuse"
    raise ContractError("package tag conflicts with candidate digest")


def _flatten_package_versions(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise ContractError("package metadata is invalid")
    if all(type(entry) is dict for entry in value):
        return value
    if not all(type(page) is list for page in value):
        raise ContractError("package metadata is invalid")

    entries: list[dict[str, object]] = []
    for page in value:
        if not all(type(entry) is dict for entry in page):
            raise ContractError("package metadata is invalid")
        entries.extend(page)
    return entries


def _required_string(value: dict[str, object], key: str) -> str:
    result = value.get(key)
    if type(result) is not str:
        raise ContractError("package metadata is invalid")
    return result


def _load_json_file(value: str) -> object:
    payload = Path(value).read_bytes()
    if not payload or len(payload) > MAX_JSON_BYTES:
        raise ContractError("JSON authority is invalid")
    return json.loads(payload.decode("utf-8"))


def build_command(
    *,
    revision: str,
    mode: str,
    actor: str,
    runtime_config_digest: str | None = None,
) -> str:
    revision = validate_revision(revision)
    actor = validate_actor(actor)
    if mode == "keep":
        if runtime_config_digest not in (None, ""):
            raise ContractError("keep mode must not include a runtime config digest")
        return f"{COMMAND_NAME} {revision} keep {actor}"
    if mode == "update":
        if runtime_config_digest is None:
            raise ContractError("update mode requires a runtime config digest")
        digest = validate_digest(runtime_config_digest)
        return f"{COMMAND_NAME} {revision} update {digest} {actor}"
    raise ContractError("release mode is invalid")


def parse_command(value: str) -> dict[str, str | None]:
    keep_match = KEEP_COMMAND_PATTERN.fullmatch(value)
    if keep_match is not None:
        return {
            "actor": validate_actor(keep_match.group(2)),
            "mode": "keep",
            "revision": validate_revision(keep_match.group(1)),
            "runtimeConfigDigest": None,
        }

    update_match = UPDATE_COMMAND_PATTERN.fullmatch(value)
    if update_match is not None:
        return {
            "actor": validate_actor(update_match.group(3)),
            "mode": "update",
            "revision": validate_revision(update_match.group(1)),
            "runtimeConfigDigest": validate_digest(update_match.group(2)),
        }
    raise ContractError("restricted deployment command is invalid")


def build_bootstrap_command(
    *,
    revision: str,
    runtime_config_digest: str,
    actor: str,
) -> str:
    return " ".join(
        (
            BOOTSTRAP_COMMAND_NAME,
            validate_revision(revision),
            validate_digest(runtime_config_digest),
            validate_actor(actor),
        )
    )


def parse_bootstrap_command(value: str) -> dict[str, str]:
    match = BOOTSTRAP_COMMAND_PATTERN.fullmatch(value)
    if match is None:
        raise ContractError("restricted bootstrap command is invalid")
    return {
        "actor": validate_actor(match.group(3)),
        "revision": validate_revision(match.group(1)),
        "runtimeConfigDigest": validate_digest(match.group(2)),
    }


def validate_publish_result(
    *,
    revision: str,
    api_digest: str,
    web_digest: str,
    mode: str,
    runtime_config_digest: str | None,
) -> dict[str, str | None]:
    revision = validate_revision(revision)
    api_digest = validate_digest(api_digest)
    web_digest = validate_digest(web_digest)
    if mode == "keep":
        if runtime_config_digest not in (None, ""):
            raise ContractError("keep mode must not publish a runtime config digest")
        runtime_config_digest = None
    elif mode == "update":
        if runtime_config_digest is None:
            raise ContractError("update mode requires a runtime config digest")
        runtime_config_digest = validate_digest(runtime_config_digest)
    else:
        raise ContractError("release mode is invalid")
    return {
        "apiDigest": api_digest,
        "revision": revision,
        "runtimeConfigDigest": runtime_config_digest,
        "runtimeConfigMode": mode,
        "webDigest": web_digest,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-command")
    build.add_argument("--revision", required=True)
    build.add_argument("--mode", required=True)
    build.add_argument("--runtime-config-digest")
    build.add_argument("--actor", required=True)

    parse = subparsers.add_parser("parse-command")
    parse.add_argument("--value", required=True)

    build_bootstrap = subparsers.add_parser("build-bootstrap-command")
    build_bootstrap.add_argument("--revision", required=True)
    build_bootstrap.add_argument("--runtime-config-digest", required=True)
    build_bootstrap.add_argument("--actor", required=True)

    parse_bootstrap = subparsers.add_parser("parse-bootstrap-command")
    parse_bootstrap.add_argument("--value", required=True)

    publish = subparsers.add_parser("validate-publish")
    publish.add_argument("--revision", required=True)
    publish.add_argument("--api-digest", required=True)
    publish.add_argument("--web-digest", required=True)
    publish.add_argument("--mode", required=True)
    publish.add_argument("--runtime-config-digest")

    publish_request = subparsers.add_parser("validate-publish-request")
    publish_request.add_argument("--revision", required=True)
    publish_request.add_argument("--validation-run-id", required=True)

    publish_authority = subparsers.add_parser("validate-publish-authority")
    publish_authority.add_argument("--revision", required=True)
    publish_authority.add_argument("--validation-run-id", required=True)
    publish_authority.add_argument("--repository", required=True)
    publish_authority.add_argument("--run-json-file", required=True)

    classify_tag = subparsers.add_parser("classify-package-tag")
    classify_tag.add_argument("--revision", required=True)
    classify_tag.add_argument("--digest", required=True)
    classify_tag.add_argument("--versions-json-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "build-command":
            print(
                build_command(
                    revision=arguments.revision,
                    mode=arguments.mode,
                    runtime_config_digest=arguments.runtime_config_digest,
                    actor=arguments.actor,
                )
            )
            return 0
        if arguments.command == "parse-command":
            print(
                json.dumps(
                    parse_command(arguments.value),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        if arguments.command == "build-bootstrap-command":
            print(
                build_bootstrap_command(
                    revision=arguments.revision,
                    runtime_config_digest=arguments.runtime_config_digest,
                    actor=arguments.actor,
                )
            )
            return 0
        if arguments.command == "parse-bootstrap-command":
            print(
                json.dumps(
                    parse_bootstrap_command(arguments.value),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        if arguments.command == "validate-publish":
            print(
                json.dumps(
                    validate_publish_result(
                        revision=arguments.revision,
                        api_digest=arguments.api_digest,
                        web_digest=arguments.web_digest,
                        mode=arguments.mode,
                        runtime_config_digest=arguments.runtime_config_digest,
                    ),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        if arguments.command == "validate-publish-request":
            print(
                json.dumps(
                    validate_publish_request(
                        revision=arguments.revision,
                        validation_run_id=arguments.validation_run_id,
                    ),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        if arguments.command == "validate-publish-authority":
            print(
                json.dumps(
                    validate_publish_authority(
                        revision=arguments.revision,
                        validation_run_id=arguments.validation_run_id,
                        repository=arguments.repository,
                        run=_load_json_file(arguments.run_json_file),
                    ),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        if arguments.command == "classify-package-tag":
            print(
                classify_package_tag(
                    revision=arguments.revision,
                    digest=arguments.digest,
                    versions=_load_json_file(arguments.versions_json_file),
                )
            )
            return 0
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError):
        print("release contract validation failed", file=sys.stderr)
        return 64
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
