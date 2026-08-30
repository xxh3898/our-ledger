#!/usr/bin/env python3
"""Pure validation for the immutable release transport source contract."""

from __future__ import annotations

import argparse
import json
import re
import sys


ZERO_SHA = "0" * 40
ZERO_DIGEST = "sha256:" + ("0" * 64)
COMMAND_NAME = "deploy-our-ledger-v1"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
ACTOR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
KEEP_COMMAND_PATTERN = re.compile(
    rf"{COMMAND_NAME} ([0-9a-f]{{40}}) keep ([A-Za-z0-9][A-Za-z0-9_-]{{0,63}})"
)
UPDATE_COMMAND_PATTERN = re.compile(
    rf"{COMMAND_NAME} ([0-9a-f]{{40}}) update (sha256:[0-9a-f]{{64}}) "
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

    publish = subparsers.add_parser("validate-publish")
    publish.add_argument("--revision", required=True)
    publish.add_argument("--api-digest", required=True)
    publish.add_argument("--web-digest", required=True)
    publish.add_argument("--mode", required=True)
    publish.add_argument("--runtime-config-digest")
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
    except ContractError:
        print("release contract validation failed", file=sys.stderr)
        return 64
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
