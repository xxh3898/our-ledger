from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ci_tools import docker_cache as cache
from scripts.ci_tools import verify_cache_fixture as fixture
from scripts.ci_tools.test_change_classifier import job_block


ROOT = cache.ROOT
PUSH = {
    "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "xxh3898/our-ledger",
    "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/dev",
    "GITHUB_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/full-ci.yml@refs/heads/dev",
    "GITHUB_JOB": "fresh-host-bootstrap", "CI_DOCKER_CACHE_MODE": "gha-write",
    "CI_DOCKER_CACHE_READY": "true", "DOCKER_DEFAULT_PLATFORM": "linux/amd64",
    "ACTIONS_RUNTIME_TOKEN": "synthetic-runtime-token", "ACTIONS_RESULTS_URL": "https://cache.example.invalid/",
}
PR = {**PUSH, "GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_REF": "dev",
      "GITHUB_REF": "refs/pull/123/merge",
      "GITHUB_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/full-ci.yml@refs/pull/123/merge"}


def arguments(family="api", *, clean=True, platform=None):
    result = ["--progress", "plain", "--pull"]
    if clean:
        result += ["--no-cache"]
    if platform:
        result += ["--platform", platform]
    return [*result, "--network", "none", "--label", "fixture=value",
            "--tag", "our-ledger-test:fixture", "--file", str(ROOT / cache.DOCKERFILES[family]), str(ROOT)]


class PolicyTest(unittest.TestCase):
    def test_only_direct_dev_events_enable_cache(self):
        self.assertEqual(cache.event_mode(PR), "gha-read")
        self.assertEqual(cache.event_mode(PUSH), "gha-write")
        for change in ({"GITHUB_ACTIONS": "false"}, {"GITHUB_REPOSITORY": "fork/our-ledger"},
                       {"GITHUB_EVENT_NAME": "workflow_dispatch"}, {"GITHUB_EVENT_NAME": "workflow_call"},
                       {"GITHUB_EVENT_NAME": "pull_request_target"}, {"GITHUB_EVENT_NAME": "unknown"},
                       {"GITHUB_BASE_REF": "main"}, {"GITHUB_REF": "refs/heads/main"},
                       {"GITHUB_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/deploy.yml@refs/heads/main"},
                       {"GITHUB_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/publish-release.yml@refs/heads/dev"},
                       {"GITHUB_WORKFLOW_REF": ""}, {"GITHUB_REF": "refs/pull/123/head"}):
            with self.subTest(change=change):
                self.assertEqual(cache.event_mode({**PR, **change}), "disabled")
        self.assertEqual(cache.event_mode({}), "disabled")

    def test_one_writer_job_per_family_and_every_pr_is_read_only(self):
        for family, jobs in cache.READERS.items():
            writers = []
            for job in jobs:
                with self.subTest(family=family, job=job):
                    mode = cache.build_mode(family, {**PUSH, "GITHUB_JOB": job})
                    if mode == "gha-write":
                        writers.append(job)
                    self.assertEqual(cache.build_mode(family, {**PR, "GITHUB_JOB": job}), "gha-read")
                    self.assertEqual(cache.build_mode(family, {**PUSH, "GITHUB_JOB": job, "CI_DOCKER_CACHE_MODE": "gha-read"}), "gha-read")
            self.assertEqual(writers, [cache.WRITERS[family]])
            for job in ("production-runtime", "deploy", "publish", "future", ""):
                self.assertEqual(cache.build_mode(family, {**PUSH, "GITHUB_JOB": job}), "disabled")

    def test_unset_is_disabled_and_unknown_modes_fail_closed(self):
        self.assertEqual(cache.build_mode("api", {key: value for key, value in PUSH.items() if key != "CI_DOCKER_CACHE_MODE"}), "disabled")
        for mode in ("", "auto", "gha-write\n", "local", "true"):
            with self.subTest(mode=mode), patch.object(cache.subprocess, "run") as run, self.assertRaises(ValueError):
                cache.build_image("api", arguments(), {**PUSH, "CI_DOCKER_CACHE_MODE": mode})
            run.assert_not_called()


class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="our-ledger-cache-inputs-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for family in cache.DOCKERFILES:
            for source in cache.dependency_inputs(family, ROOT):
                target = self.root / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

    def test_family_platform_and_privileged_namespaces_are_disjoint(self):
        scopes = {cache.cache_scope(family, platform, self.root)
                  for family in cache.DOCKERFILES for platform in ("linux/amd64", "linux/arm64")}
        self.assertEqual(len(scopes), 4)
        for scope in scopes:
            self.assertRegex(scope, r"^our-ledger-ci-v1-(api|web)-linux-(amd64|arm64)-dev-[0-9a-f]{24}$")
            self.assertNotIn(scope, {"our-ledger-api-arm64", "our-ledger-web-arm64", "our-ledger-runtime-config-arm64"})
        for platform in ("linux/arm64,linux/amd64", "darwin/arm64", "linux/arm/v7", "linux/amd64\n"):
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                cache.cache_scope("api", platform, self.root)

    def test_every_effective_dockerfile_ignore_and_dependency_input_changes_generation(self):
        for family in cache.DOCKERFILES:
            initial = cache.cache_scope(family, "linux/amd64", self.root)
            for path in cache.dependency_inputs(family, self.root):
                with self.subTest(family=family, path=path.relative_to(self.root)):
                    original = path.read_bytes()
                    path.write_bytes(original + b"\nchanged input\n")
                    self.assertNotEqual(initial, cache.cache_scope(family, "linux/amd64", self.root))
                    path.write_bytes(original)

    def test_source_only_change_uses_buildkit_checksum_not_commit_namespace(self):
        for family, source in {"api": "backend/src/main/Example.java", "web": "frontend/src/example.ts"}.items():
            initial = cache.cache_scope(family, "linux/amd64", self.root)
            target = self.root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("source A", encoding="utf-8")
            target.write_text("source B", encoding="utf-8")
            self.assertEqual(initial, cache.cache_scope(family, "linux/amd64", self.root))
        for family in ("api", "web"):
            self.assertNotIn(self.root / ".dockerignore", cache.dependency_inputs(family, self.root))

    def test_added_gradle_input_and_changed_base_image_invalidate(self):
        before = cache.cache_scope("api", "linux/amd64", self.root)
        (self.root / "backend/gradle/dependency-locks").mkdir()
        (self.root / "backend/gradle/dependency-locks/test.lockfile").write_text("dependency:2", encoding="utf-8")
        self.assertNotEqual(before, cache.cache_scope("api", "linux/amd64", self.root))
        dockerfile = self.root / cache.DOCKERFILES["api"]
        before = cache.cache_scope("api", "linux/amd64", self.root)
        dockerfile.write_text(dockerfile.read_text(encoding="utf-8").replace("eclipse-temurin:", "changed-base:"), encoding="utf-8")
        self.assertNotEqual(before, cache.cache_scope("api", "linux/amd64", self.root))

    def test_missing_or_symlinked_input_cannot_create_a_cache_scope(self):
        target = self.root / "frontend/package-lock.json"
        target.unlink()
        with self.assertRaises(ValueError):
            cache.cache_scope("web", "linux/amd64", self.root)
        target.symlink_to(self.root / "frontend/package.json")
        with self.assertRaises(ValueError):
            cache.cache_scope("web", "linux/amd64", self.root)


class BuildTest(unittest.TestCase):
    def run_build(self, environment, results, family="api", args=None):
        with patch.object(cache.subprocess, "run", side_effect=results) as run, contextlib.redirect_stdout(io.StringIO()) as output:
            result = cache.build_image(family, args or arguments(family), environment)
        self.assertNotIn("synthetic-runtime-token", output.getvalue())
        self.assertNotIn("cache.example.invalid", output.getvalue())
        return result, run.call_args_list

    def test_disabled_main_release_and_local_preserve_exact_original_build(self):
        for env in ({}, {**PUSH, "CI_DOCKER_CACHE_MODE": "disabled"}, {**PR, "GITHUB_BASE_REF": "main"},
                    {**PUSH, "GITHUB_EVENT_NAME": "workflow_call"},
                    {**PUSH, "GITHUB_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/deploy.yml@refs/heads/main"}):
            for clean in (False, True):
                args = arguments(clean=clean)
                result, calls = self.run_build(env, [subprocess.CompletedProcess([], 0)], args=args)
                self.assertEqual(result, 0)
                self.assertEqual(calls[0].args[0], ["docker", "build", *args])
                self.assertEqual(len(calls), 1)

    def test_missing_runtime_or_setup_uses_no_cache_and_preserves_failure(self):
        for change in ({"ACTIONS_RUNTIME_TOKEN": ""}, {"ACTIONS_RESULTS_URL": ""},
                       {"ACTIONS_RESULTS_URL": "http://cache.example.invalid"}, {"ACTIONS_RUNTIME_TOKEN": "bad\nvalue"},
                       {"CI_DOCKER_CACHE_READY": "false"}, {"CI_DOCKER_CACHE_READY": ""}):
            result, calls = self.run_build({**PUSH, **change}, [subprocess.CompletedProcess([], 17)], args=arguments(clean=False))
            self.assertEqual(result, 17)
            self.assertEqual(calls[0].args[0][:3], ["docker", "build", "--no-cache"])
            self.assertNotIn("ACTIONS_RUNTIME_TOKEN", calls[0].kwargs["env"])
            self.assertEqual(len(calls), 1)

    def test_cache_hit_or_miss_loads_same_tag_and_preserves_arguments(self):
        for env in (PUSH, PR):
            result, calls = self.run_build(env, [subprocess.CompletedProcess([], 0)])
            command = calls[0].args[0]
            self.assertEqual(result, 0)
            self.assertEqual(command[:4], ["docker", "buildx", "build", "--load"])
            self.assertIn("--pull", command)
            self.assertNotIn("--no-cache", command)
            self.assertEqual(command[-1], str(ROOT))
            for option in ("--file", "--tag", "--label", "--network"):
                self.assertEqual(command[command.index(option) + 1], arguments()[arguments().index(option) + 1])
            self.assertIn("version=2", command[command.index("--cache-from") + 1])
            self.assertEqual("--cache-to" in command, env == PUSH)
            if env == PUSH:
                self.assertIn("mode=max,ignore-error=true,timeout=60s", command[command.index("--cache-to") + 1])
            self.assertNotIn("synthetic-runtime-token", " ".join(command))
            self.assertNotIn("cache.example.invalid", " ".join(command))

    def test_buildx_or_cache_failure_retries_clean_and_never_skips_failure(self):
        for failure in (subprocess.CompletedProcess([], 1), OSError("missing buildx")):
            for final in (0, 9):
                result, calls = self.run_build(PUSH, [failure, subprocess.CompletedProcess([], final)])
                self.assertEqual(result, final)
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[1].args[0], ["docker", "build", *arguments()])
                self.assertNotIn("--cache-from", calls[1].args[0])

    def test_native_daemon_platform_and_explicit_platform(self):
        env = {key: value for key, value in PUSH.items() if key != "DOCKER_DEFAULT_PLATFORM"}
        result, calls = self.run_build(env, [subprocess.CompletedProcess([], 0, "linux/arm64\n"), subprocess.CompletedProcess([], 0)])
        self.assertEqual(result, 0)
        self.assertIn("{{.Server.Os}}/{{.Server.Arch}}", calls[0].args[0])
        self.assertIn("linux/arm64", calls[1].args[0])
        result, calls = self.run_build(PUSH, [subprocess.CompletedProcess([], 0)], args=arguments(platform="linux/arm64"))
        self.assertEqual(result, 0)
        self.assertEqual(calls[0].args[0].count("--platform"), 1)

    def test_build_arguments_are_rejected_before_any_docker_execution(self):
        for family in ("api", "web"):
            for value in ("REVISION=" + "a" * 40, "TOKEN=synthetic-secret", "TOKEN"):
                with self.subTest(family=family, value=value), patch.object(cache.subprocess, "run") as run, self.assertRaises(ValueError):
                    cache.build_image(family, ["--build-arg", value, *arguments(family)], PUSH)
                run.assert_not_called()

    def test_runtime_config_is_not_a_cache_family(self):
        self.assertEqual(set(cache.DOCKERFILES), {"api", "web"})
        for mode in ("disabled", "gha-read", "gha-write"):
            with self.subTest(mode=mode), patch.object(cache.subprocess, "run") as run, self.assertRaises(ValueError):
                cache.build_image("runtime-config", arguments(), {**PUSH, "CI_DOCKER_CACHE_MODE": mode})
            run.assert_not_called()
        with self.assertRaises(ValueError):
            cache.cache_scope("runtime-config", "linux/arm64")

    def test_arbitrary_context_dockerfile_and_cache_or_publish_flags_are_rejected(self):
        changes = [arguments()[:-1] + ["/tmp/foreign"], arguments("web"),
                   ["--cache-to", "type=registry", *arguments()], ["--push", *arguments()],
                   ["--output", "type=registry", *arguments()], ["--secret", "id=credential", *arguments()]]
        for args in changes:
            with self.subTest(args=args), patch.object(cache.subprocess, "run") as run, self.assertRaises(ValueError):
                cache.build_image("api", args, PUSH)
            run.assert_not_called()


class WorkflowTest(unittest.TestCase):
    def test_exact_six_call_sites_and_five_original_builds(self):
        sites = {"backup-restore": ["api"], "production-bootstrap": ["api"],
                 "fresh-host-bootstrap": ["api", "web"], "observability": ["api", "web"]}
        total = 0
        for name, families in sites.items():
            source = (ROOT / f"scripts/verify-{name}.sh").read_text(encoding="utf-8")
            actual = re.findall(r'^python3 -B "\$ROOT_DIR/scripts/ci_tools/docker_cache.py" build ([a-z-]+)', source, re.M)
            self.assertEqual(actual, families)
            blocks = re.findall(r'^python3 -B "\$ROOT_DIR/scripts/ci_tools/docker_cache.py" build ([a-z-]+)(.*?)(?=^\S|\Z)', source, re.M | re.S)
            for _, block in blocks:
                self.assertNotIn("--build-arg", block)
            total += len(actual)
            self.assertEqual(len(re.findall(r"^docker build", source, re.M)), int(name == "fresh-host-bootstrap"))
        self.assertEqual(total, 6)
        production = (ROOT / "scripts/verify-production-runtime.sh").read_text(encoding="utf-8")
        self.assertEqual(production.count("docker build --progress plain --no-cache --pull"), 2)
        self.assertNotIn("docker_cache.py", production)
        for name in ("runtime-config-evolution", "release-transport"):
            source = (ROOT / f"scripts/verify-{name}.sh").read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r"^docker build", source, re.M)), 1)
            self.assertNotIn("docker_cache.py", source)
            self.assertIn('--build-arg "REVISION=$git_head"', source)
            self.assertIn("--platform linux/arm64", source)
            self.assertIn("--network none", source)

    def test_workflow_has_one_writer_job_and_setup_failures_cannot_skip_verification(self):
        source = (ROOT / ".github/workflows/full-ci.yml").read_text(encoding="utf-8")
        jobs = set().union(*cache.READERS.values())
        self.assertEqual(set(cache.WRITERS.values()), {"fresh-host-bootstrap"})
        for name in jobs:
            body = job_block(source, name)
            self.assertIn("uses: ./.github/actions/prepare-ci-docker-cache", body)
            self.assertIn("uses: docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c", body)
            self.assertIn("driver: docker-container", body)
            self.assertIn("cache-binary: false", body)
            self.assertIn("cleanup: true", body)
            self.assertEqual(body.count("continue-on-error: true"), 2)
            self.assertIn("steps.cache-builder.outcome == 'success' && steps.cache-runtime.outputs.ready == 'true'", body)
            self.assertEqual("docker_cache_mode == 'gha-write' && 'gha-read'" in body, name not in set(cache.WRITERS.values()))
            verification = body[body.rfind("      - name:"):]
            self.assertNotIn("if:", verification)
            self.assertNotIn("continue-on-error:", verification)
            self.assertIn(f"run: ./scripts/verify-{name}.sh", verification)
        self.assertEqual(source.count("uses: ./.github/actions/prepare-ci-docker-cache"), 4)
        for name in ("production-runtime", "runtime-config-evolution", "release-transport", "host-state", "monitor-policy"):
            self.assertNotIn("CI_DOCKER_CACHE", job_block(source, name))
            self.assertNotIn("setup-buildx-action", job_block(source, name))
        self.assertIn("docker_cache_mode: ${{ steps.docker-cache.outputs.mode }}", job_block(source, "repository"))
        for filename in ("deploy.yml", "publish-release.yml"):
            privileged = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
            self.assertNotIn("our-ledger-ci-v1", privileged)
            self.assertNotIn("CI_DOCKER_CACHE", privileged)
            for family in ("api", "web", "runtime-config"):
                self.assertIn(f"cache-from: type=gha,scope=our-ledger-{family}-arm64", privileged)
                self.assertIn(f"cache-to: type=gha,mode=max,scope=our-ledger-{family}-arm64", privileged)


class RuntimeActionTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node runtime is only needed for the local JavaScript action fixture")
    def test_action_exports_only_allowlisted_values_without_output_or_newline_injection(self):
        for change, ready in (({}, True), ({"ACTIONS_RUNTIME_TOKEN": ""}, False),
                              ({"ACTIONS_RESULTS_URL": "bad\nINJECTED=value"}, False)):
            with tempfile.TemporaryDirectory(prefix="our-ledger-cache-action-") as temporary:
                env_file, output_file = Path(temporary) / "env", Path(temporary) / "output"
                result = subprocess.run(["node", str(ROOT / ".github/actions/prepare-ci-docker-cache/index.js")],
                                        env={**os.environ, **PUSH, **change, "GITHUB_ENV": str(env_file),
                                             "GITHUB_OUTPUT": str(output_file), "GITHUB_TOKEN": "synthetic-privileged-token"},
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout + result.stderr, "")
                self.assertEqual(output_file.read_text(encoding="utf-8"), f"ready={str(ready).lower()}\n")
                if ready:
                    self.assertEqual(env_file.read_text(encoding="utf-8"), "ACTIONS_RUNTIME_TOKEN=synthetic-runtime-token\nACTIONS_RESULTS_URL=https://cache.example.invalid/\n")
                else:
                    self.assertFalse(env_file.exists())


class ManualFixtureTest(unittest.TestCase):
    def test_exact_builder_names_match_cleanup_receipt_project_and_distinct_tasks(self):
        self.assertEqual(fixture.BUILDER_TASKS, {"cold": "issue-123-cache-fixture-cold", "warm": "issue-123-cache-fixture-warm"})
        for phase, task in fixture.BUILDER_TASKS.items():
            self.assertEqual(fixture.BUILDERS[phase], f"dev-our-ledger-{task}")

    def test_shared_duplicate_noncontainer_and_nonempty_builders_are_rejected(self):
        for cold, warm in (("default", "desktop-linux"), (fixture.BUILDERS["cold"],) * 2,
                           ("our-ledger-ci-cache-fixture-cold", "our-ledger-ci-cache-fixture-warm"),
                           (fixture.BUILDERS["warm"], fixture.BUILDERS["cold"])):
            with patch.object(fixture, "run") as run, self.assertRaises(ValueError):
                fixture.validate_builders(cold, warm)
            run.assert_not_called()
        for results in (("Driver: docker\nStatus: running\n",),
                        ("Driver: docker-container\nStatus: stopped\n",),
                        ("Driver: docker-container\nStatus: running\n", "existing-cache-record\n")):
            with patch.object(fixture, "run", side_effect=[subprocess.CompletedProcess([], 0, item) for item in results]), self.assertRaises(ValueError):
                fixture.validate_builders(fixture.BUILDERS["cold"], fixture.BUILDERS["warm"])

    def test_fixture_requires_separate_empty_builders_without_creating_or_pruning_them(self):
        replies = [subprocess.CompletedProcess([], 0, item) for item in
                   ("Driver: docker-container\nStatus: running\n", "", "Driver: docker-container\nStatus: running\n", "")]
        with patch.object(fixture, "run", side_effect=replies) as run:
            fixture.validate_builders(fixture.BUILDERS["cold"], fixture.BUILDERS["warm"])
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ["inspect", "du", "inspect", "du"])


if __name__ == "__main__":
    unittest.main()
