from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.ci_tools import ci_timing


class TimingTest(unittest.TestCase):
    def test_monotonic_integer_milliseconds_and_exact_safe_output(self):
        with patch.object(ci_timing, "monotonic_ns", return_value=3_234_567_891), \
             patch.object(ci_timing.time, "time", side_effect=AssertionError("wall clock")):
            self.assertEqual(ci_timing.marker("production-bootstrap-08", "1000000000"),
                             "ci-timing stage=production-bootstrap-08 elapsed_ms=2234")
            self.assertEqual(ci_timing.marker("backup-restore-10", "3234567891"),
                             "ci-timing stage=backup-restore-10 elapsed_ms=0")

    def test_rejects_noncanonical_future_and_hostile_inputs_without_echo(self):
        cases = [("end", stage, "1") for stage in (
            "secret@example.test", "/private/path", "production-bootstrap-13", "backup-restore-00",
            "production-bootstrap-08\ncredential=secret", "arbitrary-safe-name",
        )]
        cases += [("end", "backup-restore-10", start) for start in (
            "-1", "1.0", "+1", "01", "1\n", " 1", "NaN", "100000000000000000000", "11",
        )]
        cases += [("run", "secret"), ("begin", "secret"), ("end",), ()]
        for arguments in cases:
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(arguments=arguments), \
                 patch.object(ci_timing, "monotonic_ns", return_value=10), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(ci_timing.main(list(arguments)), 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "invalid CI timing input\n")

    def test_begin_only_returns_a_monotonic_integer(self):
        stdout = io.StringIO()
        with patch.object(ci_timing, "monotonic_ns", return_value=123), \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(ci_timing.main(["begin"]), 0)
        self.assertEqual(stdout.getvalue(), "123\n")

    def test_uses_shared_os_epoch_on_macos_python_39_and_linux(self):
        with patch.object(ci_timing.time, "clock_gettime_ns", return_value=123) as read, \
             patch.object(ci_timing.time, "monotonic_ns", side_effect=AssertionError("process epoch")):
            self.assertEqual(ci_timing.monotonic_ns(), 123)
        read.assert_called_once_with(ci_timing.time.CLOCK_MONOTONIC)

    def test_clock_failure_does_not_echo_exception_path_or_environment(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(ci_timing, "monotonic_ns", side_effect=OSError("private/path secret")), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(ci_timing.main(["begin"]), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "invalid CI timing input\n")

    def test_markers_preserve_bash_errexit_pipefail_and_exit_cleanup(self):
        helper = Path(ci_timing.__file__).resolve()
        for command, expected in (
            ("exit 37", 37),
            ("false | true", 1),
            ("stage() { false; printf leaked; }; stage", 1),
            ("true", 0),
        ):
            with self.subTest(command=command):
                completed = subprocess.run(
                    ["bash", "-c", '''set -euo pipefail
trap 'result=$?; printf "cleanup-status=%s\\n" "$result"; exit "$result"' EXIT
started="$("$1" -B "$2" begin)"
''' + command + '''
"$1" -B "$2" end production-bootstrap-01 "$started"
''', "timing-test", sys.executable, str(helper)],
                    env={**os.environ, "SECRET_SENTINEL": "must-not-appear"},
                    capture_output=True, text=True, check=False,
                )
            self.assertEqual(completed.returncode, expected, completed.stderr)
            self.assertIn(f"cleanup-status={expected}\n", completed.stdout)
            self.assertNotIn("must-not-appear", completed.stdout + completed.stderr)
            self.assertNotIn("leaked", completed.stdout)
            self.assertEqual("ci-timing " in completed.stdout, expected == 0)


if __name__ == "__main__":
    unittest.main()
