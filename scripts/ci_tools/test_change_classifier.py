from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ci_tools import change_classifier as ci


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/full-ci.yml"
BACKEND = ci.BACKEND_ROOT
TESTS = ci.BACKEND_TEST_ROOT
ENVIRONMENT = {
    "CI_EVENT_NAME": "pull_request",
    "CI_BASE_REF": "dev",
    "CI_REPOSITORY": "xxh3898/our-ledger",
    "CI_REF": "refs/pull/151/merge",
    "CI_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/full-ci.yml@refs/pull/151/merge",
    "CI_BASE_SHA": "1" * 40,
    "CI_HEAD_SHA": "2" * 40,
}
MATRIX = (
    ("docs-only", ["docs/05-frontend/quick-entry.md", "README.md"], set()),
    ("frontend-only", ["frontend/src/App.tsx", "frontend/src/App.test.tsx", "docs/07-quality/testing-strategy.md"], {"frontend"}),
    ("backend-only", [BACKEND + "budget/BudgetService.java", TESTS + "BudgetIntegrationTest.java"], {"backend"}),
    ("ops-runtime", ["backend/src/main/resources/db/migration/V9__example.sql"], ci.ALL_JOBS - {"repository"}),
    ("ops-runtime", ["infra/nginx/nginx.conf"], ci.ALL_JOBS - {"repository"}),
    ("mixed/unknown", ["frontend/src/App.tsx", BACKEND + "budget/BudgetService.java"], ci.ALL_JOBS - {"repository"}),
    ("mixed/unknown", ["new-subsystem/handler.py"], ci.ALL_JOBS - {"repository"}),
)


def job_block(workflow: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow, re.M | re.S)
    if match is None:
        raise AssertionError(f"missing job {name}")
    return match[0]


def needs_for(decision: dict[str, str]) -> dict:
    result = {"repository": {"result": "success", "outputs": decision}}
    for name in ci.ALL_JOBS - {"repository"}:
        flag = {"backend": "run_backend", "frontend": "run_frontend"}.get(name, "run_full")
        result[name] = {"result": "success" if decision[flag] == "true" else "skipped"}
    return result


class ChangeClassifierTest(unittest.TestCase):
    def test_change_matrix_selects_only_expected_jobs(self):
        for category, paths, expected in MATRIX:
            with self.subTest(category=category, paths=paths):
                decision = ci.classify_paths(paths)
                self.assertEqual(decision["category"], category)
                needs = needs_for(decision)
                selected = {name for name, job in needs.items() if name != "repository" and job["result"] == "success"}
                self.assertEqual(selected, expected)
                ci.check_gate(needs)

    def test_authority_paths_cannot_enter_fast_frontend_or_backend_route(self):
        authority_paths = [
            "infra/README.md", "scripts/production-example.sh", "scripts/backup-example.sh",
            "scripts/offsite-example.sh", "scripts/verify-frontend.sh", "scripts/verify.sh",
            "scripts/ci_tools/change_classifier.py", ".github/workflows/full-ci.yml",
            ".github/workflows/deploy.yml", ".github/workflows/frontend-ci.yml",
            "compose.prod.yaml", "runtime-manifest.json", "runtime-config.Dockerfile",
            ".env.example", ".dockerignore", "AGENTS.md", "frontend/package.json",
            "frontend/package-lock.json", "frontend/vite.config.ts", "frontend/tsconfig.app.json",
            "frontend/index.html", "frontend/public/manifest.webmanifest",
            "frontend/scripts/verify-app-start-build.mjs", "frontend/src/new-module.wasm",
            "backend/build.gradle.kts", "backend/gradlew", "backend/gradle/wrapper/gradle-wrapper.jar",
            "backend/src/main/resources/application-production.yml", "backend/src/test/resources/application-test.yml",
            BACKEND + "security/CloudflareAccessSecurityConfiguration.java",
            BACKEND + "bootstrap/HouseholdBootstrapService.java", BACKEND + "ops/MigrationRuntimeGuard.java",
            BACKEND + "identity/User.java", BACKEND + "household/HouseholdRepository.java",
            BACKEND + "recurring/RecurringScheduler.java", BACKEND + "OurLedgerApplication.java",
            BACKEND + "budget/BudgetController.java", BACKEND + "budget/BudgetCreateRequest.java",
            BACKEND + "budget/BudgetResponse.java", BACKEND + "budget/NewSecurityConfiguration.java",
            BACKEND + "newpackage/FutureService.java", TESTS + "CloudflareAccessSecurityIntegrationTest.java",
            TESTS + "OurLedgerApplicationTest.java", "docs/03-data/schema-rules.md",
            "docs/04-api/api-conventions.md", "docs/06-security/authentication.md",
            "docs/08-operations/deployment.md", "docs/09-decisions/ADR-009-runtime-config-evolution.md",
        ]
        for path in authority_paths:
            with self.subTest(path=path):
                decision = ci.classify_paths(["frontend/src/App.tsx", path])
                self.assertEqual(decision["category"], "ops-runtime")
                self.assertTrue(all(decision[flag] == "true" for flag in ci.FLAGS))

    def test_unknown_empty_and_noncanonical_paths_select_full(self):
        for paths in [[], [""], ["/frontend/src/App.tsx"], ["frontend/src/../infra.ts"],
                      ["frontend//src/App.tsx"], ["frontend/src/evil\nname.ts"],
                      ["frontend\\src\\App.tsx"], ["future/README.md"],
                      ["docs/new-contract/readme.md"], ["docs/05-frontend/assets/example.svg"]]:
            with self.subTest(paths=paths):
                decision = ci.classify_paths(paths)
                self.assertEqual(decision["category"], "mixed/unknown")
                self.assertEqual(decision["run_full"], "true")

    def test_authority_names_are_case_insensitive_inside_fast_eligible_package(self):
        for filename in ("budgetsecurity.java", "BudgetSeCuRiTy.java", "BudgetApplication.java",
                         "budgetapplication.java", "BudgetApPlIcAtIoN.java"):
            with self.subTest(filename=filename):
                decision = ci.classify_paths([BACKEND + "budget/" + filename])
                self.assertEqual(decision["category"], "ops-runtime")
                self.assertTrue(all(decision[flag] == "true" for flag in ci.FLAGS))

    def test_non_pr_main_target_and_other_reusable_callers_are_full_without_reading_diff(self):
        changes = [
            {"CI_EVENT_NAME": "push"}, {"CI_EVENT_NAME": "workflow_dispatch"},
            {"CI_EVENT_NAME": "workflow_call"}, {"CI_BASE_REF": "main"},
            {"CI_BASE_REF": ""}, {"CI_REF": "refs/heads/dev"},
            {"CI_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/deploy.yml@refs/heads/main"},
            {"CI_WORKFLOW_REF": "xxh3898/our-ledger/.github/workflows/another-pr.yml@refs/pull/151/merge"},
            {"CI_WORKFLOW_REF": ""}, {"CI_REPOSITORY": ""},
        ]
        for change in changes:
            with self.subTest(change=change), patch.object(ci, "changed_paths") as git_diff:
                decision = ci.classify_event({**ENVIRONMENT, **change})
                self.assertEqual(decision["run_full"], "true")
                git_diff.assert_not_called()

    def test_diff_failure_or_empty_diff_selects_full(self):
        for failure in [ValueError("shape"), OSError("git missing"),
                        subprocess.CalledProcessError(1, "git"), subprocess.TimeoutExpired("git", 30)]:
            with self.subTest(failure=type(failure)), patch.object(ci, "changed_paths", side_effect=failure):
                self.assertEqual(ci.classify_event(ENVIRONMENT)["run_full"], "true")
        with patch.object(ci, "changed_paths", return_value=[]):
            self.assertEqual(ci.classify_event(ENVIRONMENT)["reason"], "empty-diff")
        with patch.object(ci, "changed_paths", return_value=["frontend/src/App.css"]):
            self.assertEqual(ci.classify_event(ENVIRONMENT)["category"], "frontend-only")

    def test_raw_diff_rejects_unsupported_modes_status_and_framing(self):
        for raw in [b"M\0a\0", b":120000 100644 " + b"1" * 40 + b" " + b"2" * 40 + b" T\0a\0",
                    b":100644 100644 " + b"1" * 40 + b" " + b"2" * 40 + b" R100\0old\0new\0"]:
            with self.subTest(raw=raw), patch.object(ci.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw)):
                self.assertEqual(ci.classify_event(ENVIRONMENT)["run_full"], "true")
        for revision in ["0" * 40, "main", "--help", "A" * 40, "1" * 39]:
            with self.subTest(revision=revision):
                self.assertEqual(ci.classify_event({**ENVIRONMENT, "CI_HEAD_SHA": revision})["run_full"], "true")


class GitDiffIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="our-ledger-ci-matrix-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet")
        self.write("frontend/src/App.tsx", "export const App = 1\n")
        self.write("infra/runtime.txt", "runtime authority\n")
        self.write("docs/05-frontend/quick-entry.md", "# Entry\n")
        self.base = self.commit()

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=CI fixture", "-c", "user.email=ci@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def classify(self):
        return ci.classify_event({**ENVIRONMENT, "CI_BASE_SHA": self.base, "CI_HEAD_SHA": self.commit()}, self.root)

    def test_rename_from_runtime_to_frontend_keeps_deleted_authority(self):
        self.git("mv", "infra/runtime.txt", "frontend/src/runtime.ts")
        self.assertEqual(self.classify()["category"], "ops-runtime")

    def test_rename_from_frontend_to_unknown_uses_full(self):
        (self.root / "future").mkdir()
        self.git("mv", "frontend/src/App.tsx", "future/App.tsx")
        self.assertEqual(self.classify()["category"], "mixed/unknown")

    def test_frontend_rename_and_delete_still_require_frontend(self):
        self.git("mv", "frontend/src/App.tsx", "frontend/src/Renamed.tsx")
        self.assertEqual(self.classify()["category"], "frontend-only")
        self.git("rm", "frontend/src/Renamed.tsx")
        self.assertEqual(self.classify()["category"], "frontend-only")

    def test_runtime_deletion_still_requires_full(self):
        self.git("rm", "infra/runtime.txt")
        self.assertEqual(self.classify()["category"], "ops-runtime")

    def test_symlink_and_executable_mode_cannot_use_fast_allowlist(self):
        (self.root / "frontend/src/linked.ts").symlink_to("App.tsx")
        self.assertEqual(self.classify()["run_full"], "true")
        self.git("rm", "frontend/src/linked.ts")
        self.git("update-index", "--chmod=+x", "frontend/src/App.tsx")
        (self.root / "frontend/src/App.tsx").chmod(0o755)
        self.assertEqual(self.classify()["run_full"], "true")

    def test_three_dot_does_not_misclassify_base_branch_changes_as_pr_changes(self):
        self.git("checkout", "--quiet", "-b", "feature")
        self.write("frontend/src/App.tsx", "export const App = 2\n")
        head = self.commit()
        self.git("checkout", "--quiet", "--detach", self.base)
        self.write("infra/runtime.txt", "base advanced\n")
        base = self.commit()
        self.assertEqual(ci.classify_event({**ENVIRONMENT, "CI_BASE_SHA": base, "CI_HEAD_SHA": head}, self.root)["category"], "frontend-only")


class GateTest(unittest.TestCase):
    def test_gate_rejects_every_failed_cancelled_or_skipped_required_job(self):
        for category, paths, _ in MATRIX:
            needs = needs_for(ci.classify_paths(paths))
            for name, result in needs.items():
                if result["result"] != "success":
                    continue
                for conclusion in ("failure", "cancelled", "skipped", None):
                    broken = copy.deepcopy(needs)
                    broken[name]["result"] = conclusion
                    with self.subTest(category=category, name=name, result=conclusion), self.assertRaises(ValueError):
                        ci.check_gate(broken)

    def test_gate_rejects_unexpected_execution_and_malformed_classifier_outputs(self):
        needs = needs_for(ci.classify_paths(["README.md"]))
        for name in ci.ALL_JOBS - {"repository"}:
            broken = copy.deepcopy(needs)
            broken[name]["result"] = "success"
            with self.subTest(name=name), self.assertRaises(ValueError):
                ci.check_gate(broken)
        for outputs in [{}, None, {"category": "future"}, {"category": "docs-only", "run_full": "false"},
                        {**needs["repository"]["outputs"], "run_full": "true"}]:
            broken = copy.deepcopy(needs)
            broken["repository"]["outputs"] = outputs
            with self.subTest(outputs=outputs), self.assertRaises(ValueError):
                ci.check_gate(broken)
        for broken in [None, [], {}, {**needs, "extra": {}}, {**needs, "frontend": None}]:
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                ci.check_gate(broken)

    def test_gate_command_uses_real_needs_json_and_nonzero_failure(self):
        for needs, expected in [(needs_for(ci.full("fixture")), 0), (None, 1)]:
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / "scripts/ci_tools/change_classifier.py"), "gate"],
                env={**os.environ, "CI_NEEDS_JSON": json.dumps(needs)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, expected)


class WorkflowContractTest(unittest.TestCase):
    def test_actual_workflow_fallback_overwrites_partial_outputs_with_full(self):
        repository = job_block(WORKFLOW.read_text(encoding="utf-8"), "repository")
        block = re.search(r"        run: \|\n(.*?)(?=\n      -|\Z)", repository, re.S)
        self.assertIsNotNone(block)
        with tempfile.TemporaryDirectory(prefix="our-ledger-ci-output-") as temporary:
            output = Path(temporary) / "output"
            failure = "python3() { printf '%s\\n' 'category=docs-only' 'run_full=false' >> \"$GITHUB_OUTPUT\"; return 1; }\n"
            result = subprocess.run(["bash", "-e", "-c", failure + textwrap.dedent(block[1])],
                                    env={**os.environ, "GITHUB_OUTPUT": str(output)},
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0)
            decision = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
            self.assertEqual(decision, ci.full("classifier-execution-failure"))
            ci.check_gate(needs_for(decision))

    def test_every_existing_job_and_verification_entrypoint_is_retained(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        names = set(re.findall(r"^  ([A-Za-z0-9_-]+):$", workflow.split("\njobs:\n", 1)[1], re.M))
        self.assertEqual(names, {*ci.ALL_JOBS, "ci-gate"})
        for name in ci.HEAVY_JOBS:
            body = job_block(workflow, name)
            self.assertIn(f"run: ./scripts/verify-{name}.sh", body)
            self.assertEqual(body.count("    if:"), 1)
            self.assertIn("    needs: repository\n", body)
            self.assertIn("if: ${{ !cancelled() && needs.repository.outputs.run_full != 'false' }}", body)
        for name in ("backend", "frontend"):
            body = job_block(workflow, name)
            self.assertIn(f"uses: ./.github/workflows/{name}-ci.yml", body)
            self.assertIn(f"if: ${{{{ !cancelled() && needs.repository.outputs.run_{name} != 'false' }}}}", body)
        repository = job_block(workflow, "repository")
        self.assertNotIn("    if:", repository)
        self.assertNotIn("    needs:", repository)
        for entrypoint in ("check-repo", "check-docs", "check-migrations", "verify-compose"):
            self.assertIn(f"run: ./scripts/{entrypoint}.sh", repository)
        local = (ROOT / "scripts/verify.sh").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'^"\$ROOT_DIR/scripts/[^\"]+"$', local, re.M)), 19)
        for name in ci.HEAVY_JOBS | {"backend", "frontend"}:
            self.assertIn(f'"$ROOT_DIR/scripts/verify-{name}.sh"', local)

    def test_gate_always_runs_and_requires_exact_existing_job_set(self):
        gate = job_block(WORKFLOW.read_text(encoding="utf-8"), "ci-gate")
        self.assertIn("    name: CI gate\n", gate)
        self.assertIn("    if: always()\n", gate)
        dependencies = re.findall(r"^      - ([a-z-]+)$", gate, re.M)
        self.assertCountEqual(dependencies, ci.ALL_JOBS)
        self.assertIn("CI_NEEDS_JSON: ${{ toJSON(needs) }}", gate)
        self.assertIn("run: python3 -B scripts/ci_tools/change_classifier.py gate", gate)

    def test_events_full_default_and_classifier_failure_fallback_are_wired(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n    branches:\n      - dev\n      - main\n", workflow)
        self.assertIn("  push:\n    branches:\n      - dev\n  workflow_dispatch:\n  workflow_call:\n", workflow)
        self.assertNotIn("paths-ignore:", workflow)
        self.assertNotIn("    paths:", workflow)
        self.assertIn("          fetch-depth: 0\n", job_block(workflow, "repository"))
        for key, value in {"CI_EVENT_NAME": "github.event_name", "CI_BASE_REF": "github.base_ref",
                           "CI_BASE_SHA": "github.event.pull_request.base.sha", "CI_HEAD_SHA": "github.event.pull_request.head.sha",
                           "CI_REPOSITORY": "github.repository", "CI_REF": "github.ref", "CI_WORKFLOW_REF": "github.workflow_ref"}.items():
            self.assertIn(f"{key}: ${{{{ {value} }}}}", workflow)
        self.assertIn("if ! python3 -B scripts/ci_tools/change_classifier.py classify; then", workflow)
        for flag in ci.FLAGS:
            self.assertIn(f"'{flag}=true'", workflow)
            self.assertIn(f"{flag}: ${{{{ steps.changes.outputs.{flag} }}}}", workflow)
        self.assertIn("'category=mixed/unknown'", workflow)

    def test_only_pr_concurrency_cancels_and_production_serialization_is_preserved(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("group: our-ledger-ci-${{ github.workflow }}-${{ github.event_name == 'pull_request' && github.event.pull_request.number || github.run_id }}", workflow)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", workflow)
        self.assertNotIn("our-ledger-production", workflow)
        for name in ("deploy.yml", "publish-release.yml"):
            source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("concurrency:\n  group: our-ledger-production\n  cancel-in-progress: false\n", source)
        deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/full-ci.yml", job_block(deploy, "validate"))
        self.assertEqual(deploy.count("vars.OUR_LEDGER_DEPLOY_ENABLED == 'true'"), 2)


if __name__ == "__main__":
    unittest.main()
