"""CI-only monotonic markers; never execute or log the measured command."""
from __future__ import annotations

import re
import sys
import time


STAGES = frozenset(
    f"{job}-{stage:02d}"
    for job, count in (
        ("production-bootstrap", 12),
        ("production-runtime", 13),
        ("backup-restore", 11),
        ("fresh-host-bootstrap", 4),
        ("observability", 8),
    )
    for stage in range(1, count + 1)
)


def monotonic_ns() -> int:
    # Python < 3.10 on macOS offsets time.monotonic_ns() per process. Shell
    # begin/end invocations need the same OS clock epoch on macOS and Linux.
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def marker(stage: str, started: str) -> str:
    if stage not in STAGES or re.fullmatch(r"0|[1-9][0-9]{0,19}", started) is None:
        raise ValueError("invalid timing input")
    now = monotonic_ns()
    start = int(started)
    if start > now:
        raise ValueError("invalid timing input")
    return f"ci-timing stage={stage} elapsed_ms={(now - start) // 1_000_000}"


def main(arguments: list[str]) -> int:
    try:
        if arguments == ["begin"]:
            print(monotonic_ns())
        elif len(arguments) == 3 and arguments[0] == "end":
            print(marker(arguments[1], arguments[2]))
        else:
            raise ValueError("invalid timing input")
    except (ValueError, OSError, AttributeError):
        # In particular, never interpolate hostile argv into usage/errors.
        print("invalid CI timing input", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
