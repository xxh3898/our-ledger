"""Deterministic contracts complement, but do not replace, Docker proofs."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from scripts.ci_tools import ci_timing


ROOT = Path(__file__).resolve().parents[2]


def source(job: str) -> str:
    return (ROOT / f"scripts/verify-{job}.sh").read_text(encoding="utf-8")


def function(value: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}$", value, re.M | re.S)
    if match is None:
        raise AssertionError(f"missing function: {name}")
    return match.group(0)


class HeavyVerificationContractTest(unittest.TestCase):
    def test_every_stage_has_fixed_success_only_begin_end_without_command_wrapper(self):
        emitted = set()
        for job, count in (("production-bootstrap", 12), ("production-runtime", 13),
                           ("backup-restore", 11), ("fresh-host-bootstrap", 4),
                           ("observability", 8)):
            value = source(job)
            markers = re.findall(r'^python3 -B "\$TIMING_HELPER" end ([a-z0-9-]+) "\$stage_started"$', value, re.M)
            with self.subTest(job=job):
                self.assertEqual(markers, [f"{job}-{stage:02d}" for stage in range(1, count + 1)])
                self.assertEqual(value.count('stage_started="$(python3 -B "$TIMING_HELPER" begin)"'), count)
                self.assertIn("set -euo pipefail", value)
                self.assertIn("trap cleanup EXIT", value)
                self.assertIn("trap 'exit 130' HUP INT TERM", value)
                self.assertNotRegex(value, r"(?:if|while)\s+.*TIMING_HELPER")
                self.assertNotIn('"$@"', function(value, "cleanup"))
                self.assertIn('exit "$original_status"', function(value, "cleanup"))
            emitted.update(markers)
        self.assertEqual(emitted, ci_timing.STAGES)

    def test_bootstrap_preserves_all_actual_jvm_input_and_failure_proofs(self):
        value = source("production-bootstrap")
        matrix = value.split("for input_name in \\\n", 1)[1].split("done", 1)[0]
        names = matrix.split("; do", 1)[0].replace("\\", "").split()
        self.assertEqual(names, ["empty", "malformed", "oversize", "unknown", "duplicate", "missing",
                                 "null", "wrong-type", "trailing", "same-email", "invalid-utf8",
                                 "utf-16le", "utf-16be", "utf-32le", "utf-32be"])
        self.assertIn('"${compose[@]}" run --rm -T --no-deps api-bootstrap', matrix)
        for label in ("unmigrated bootstrap", "partial state", "membership mismatch", "extra state",
                      "invalid bootstrap profile $invalid_profiles", "normal production bootstrap override",
                      "JPA schema mismatch", "unreachable bootstrap database"):
            self.assertRegex(value, rf'expect_failure\s+\\\n\s+"{re.escape(label)}"')
        for marker in ("household-bootstrap: created", "household-bootstrap: verified"):
            self.assertIn(f'"{marker}"', value)
        self.assertIn('run_candidate_migration "$POSTGRES_DB"', value)
        self.assertIn('"${compose[@]}" up --detach --wait --wait-timeout 240 api', value)
        self.assertIn('if [[ "$failure_status" == "124" ]]', function(value, "expect_failure"))
        self.assertIn("assert_log_safe", function(value, "expect_failure"))

    def test_template_copy_is_isolated_verified_and_has_no_retry_or_repair(self):
        value = source("production-bootstrap")
        prerequisites = function(value, "assert_template_prerequisites")
        for predicate in ("our_ledger_bootstrap_pristine", "our_ledger_bootstrap_seeded", "datdba",
                          "datacl IS NULL", "datconnlimit = -1", "datallowconn", "NOT datistemplate",
                          "pg_db_role_setting", "pg_stat_activity"):
            self.assertIn(predicate, prerequisites)
        clone = function(value, "clone_database")
        self.assertLess(clone.index("assert_template_prerequisites"), clone.index("createdb"))
        self.assertIn('--maintenance-db=postgres --template "$source_database" "$target_database"', clone)
        self.assertIn('[[ "$source_database" != "$target_database" ]]', clone)
        for proof in ("database_authority", "database_content_fingerprint", "schema_fingerprint",
                      "bootstrap_fingerprint", "pg_db_role_setting"):
            self.assertIn(proof, clone)
        self.assertEqual(clone.count("createdb"), 1)
        self.assertNotRegex(clone, r"\b(?:while|until|sleep|dropdb)\b")
        self.assertNotIn('clone_database "$POSTGRES_DB"', value)
        self.assertEqual(value.count('run_candidate_migration "$pristine_database"'), 1)
        self.assertEqual(value.count('assert_fixture_sources_unchanged\n'), 4)
        self.assertIn("COUNT(*) FROM flyway_schema_history WHERE NOT success", value)
        self.assertIn("tablename <> 'flyway_schema_history'", value)
        self.assertIn('--format=plain --restrict-key=OurLedgerSyntheticCloneProof125', value)
        self.assertNotIn("--no-owner", function(value, "database_content_fingerprint"))
        self.assertNotIn("--no-acl", function(value, "database_content_fingerprint"))

    def test_template_prerequisites_and_clone_reject_before_database_mutation(self):
        value = source("production-bootstrap")
        harness = "set -euo pipefail\n" + function(value, "assert_template_prerequisites") + "\n"
        harness += function(value, "clone_database") + '\nPOSTGRES_USER=synthetic\n'
        harness += 'postgres_query() { printf "0\\n"; }\n'
        harness += 'docker() { printf "unexpected-docker-mutation\\n"; exit 93; }\ncompose=(docker)\n'
        for command in (
            "assert_template_prerequisites our_ledger_bootstrap",
            "assert_template_prerequisites our_ledger_bootstrap_pristine",
            "clone_database our_ledger_bootstrap_pristine our_ledger_bootstrap",
            "clone_database our_ledger_bootstrap_seeded our_ledger_bootstrap_seeded",
            "clone_database our_ledger_bootstrap_pristine our_ledger_bootstrap_partial",
        ):
            with self.subTest(command=command):
                result = subprocess.run(["bash", "-c", harness + command], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("unexpected-docker-mutation", result.stdout)

    def test_backup_reuses_only_verified_target_in_strict_failure_order(self):
        value = source("backup-restore")
        self.assertNotIn("failure_project", value)
        self.assertNotIn("failure_compose", value)
        ordered = [
            '"${target_compose[@]}" up --detach --wait --wait-timeout 120 postgres',
            'target_state="$(compose_fingerprint target)"',
            'run_candidate_migration target "$runtime_temp_dir/target-migration.log"',
            'http://127.0.0.1:8080/actuator/health/readiness',
            '"${target_compose[@]}" stop --timeout 45 api >/dev/null',
            'assert_target_postgres_state healthy\n',
            '[[ "$missing_database_count" == 0 ]]',
            'expect_bounded_input_failure "$dump_path"',
            '--dbname missing_restore_target',
            'database "missing_restore_target" does not exist',
            '[[ "$(compose_fingerprint target)" == "$target_state_before_failure" ]]',
            '"${target_compose[@]}" stop --timeout 45 postgres >/dev/null',
            'assert_target_postgres_state exited\n',
            'expect_bounded_input_failure /dev/null',
            '--project-name "$target_project"',
            'assert_target_postgres_state exited\n',
            'assert_failure_artifacts_unchanged\n',
        ]
        cursor = value.index("[backup/restore 7/11]")
        for item in ordered:
            position = value.find(item, cursor)
            self.assertNotEqual(position, -1, item)
            cursor = position + len(item)
        failure_tail = value[value.index("[backup/restore 10/11]"):]
        self.assertNotRegex(failure_tail, r"\b(?:up|restart|start)\s+--")
        self.assertEqual(failure_tail.count("assert_failure_artifacts_unchanged\n"), 3)
        for proof in ("assert_failed_backup_preserved_state", "dump_sha_before", "verify --bundle-dir", "failure_observer_before",
                      'find "$failure_backup_dir" -mindepth 1'):
            self.assertIn(proof, function(value, "assert_failure_artifacts_unchanged"))
        self.assertIn('[[ "$failure_status" != 124 ]]', function(value, "expect_bounded_input_failure"))
        cleanup = function(value, "cleanup_resources")
        for project in ("source", "target"):
            self.assertIn(f'"${{{project}_compose[@]}}" down --volumes --remove-orphans', cleanup)
            self.assertIn(f'resource_residue "${project}_project"', cleanup)

    def test_runtime_clean_build_and_web_probe_assertions_are_preserved(self):
        value = source("production-runtime")
        self.assertEqual(value.count("docker build --progress plain --no-cache --pull"), 2)
        probe = value.split('nginx_config="$(')[1].split("')\"", 1)[0]
        self.assertEqual(probe.count("docker run --rm"), 1)
        self.assertIn("--add-host api:127.0.0.1", probe)
        for check in ('set -eu', 'test "$(id -u)" != "0"', "index.html", "command -v nginx",
                      "! command -v node", "! command -v npm", "! test -e /workspace",
                      "50x.html", '*.ts', '*.tsx', "nginx -t", "cat /etc/nginx/nginx.conf"):
            self.assertIn(check, probe)
        for label in ("normal production clean-schema startup", "normal production Flyway override",
                      "failed Flyway history", "JPA schema validation", "unreachable database",
                      "migration without production profile", "migration with reversed profile authority",
                      "migration with bootstrap enabled", "migration with recurring scheduler enabled",
                      "migration with Flyway disabled"):
            self.assertRegex(value, rf'expect_bounded_failure\s+\\\n\s+"{re.escape(label)}"')
        self.assertIn('restart api', value)
        self.assertIn('Commencing graceful shutdown', value)
        self.assertIn('Graceful shutdown complete', value)

    def test_cleanup_labels_require_exact_head_and_cover_all_resources(self):
        expected = {
            "io.homeserver.cleanup.environment": "development",
            "io.homeserver.cleanup.project": "our-ledger",
            "io.homeserver.cleanup.task": "issue-125-heavy-verification-bottlenecks",
            "io.homeserver.cleanup.lifecycle": "task",
            "io.homeserver.cleanup.retain": "false",
            "io.homeserver.cleanup.git-head": "a" * 40,
        }
        for job in ("production-runtime", "observability"):
            value = source(job)
            start = 'git_head="$(git -C "$ROOT_DIR" rev-parse HEAD)"'
            metadata = start + value.split(start, 1)[1].split("\nproject_name=", 1)[0]
            for head in ("a" * 40, "UNKNOWN", "a" * 39, "A" * 40, "a" * 40 + "\nextra"):
                harness = 'set -euo pipefail\nROOT_DIR=synthetic\ngit() { printf "%s" "$TEST_HEAD"; }\n'
                harness += metadata + '\nprintf "%s\\n" "${cleanup_labels[@]}"\n'
                with self.subTest(job=job, head=head):
                    result = subprocess.run(["bash", "-c", harness], env={"TEST_HEAD": head},
                                            capture_output=True, text=True)
                    if head == "a" * 40:
                        self.assertEqual(result.returncode, 0)
                        self.assertEqual(dict(line.split("=", 1) for line in result.stdout.splitlines()), expected)
                    else:
                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(result.stdout, "")
            self.assertLess(value.index('git_head="$('), value.index('mktemp -d'))
            self.assertNotIn("status --porcelain", value)
            self.assertIn('-f "$COMPOSE_FILE" -f "$override_file"', value)
            for command in re.findall(r"(?:^|\$\()(docker (?:build|create|run) [^\n]+)", value, re.M):
                self.assertIn('"${docker_labels[@]}"', command)
            self.assertIn('"${compose[@]}" down --volumes --remove-orphans --timeout 45', function(value, "cleanup"))
            self.assertIn('for group in ("services", "networks", "volumes"):', value)
            renderer = re.search(r'python3 -B - "\$override_file" "\$\{cleanup_labels\[@\]\}" <<\'PY\'\n(.*?)\nPY', value, re.S)
            self.assertIsNotNone(renderer)
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "labels.json"
                result = subprocess.run([sys.executable, "-B", "-", str(target),
                                         *(f"{key}={item}" for key, item in expected.items())],
                                        input=renderer.group(1), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                config = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(set(config), {"services", "networks", "volumes"})
                self.assertEqual(set(config["services"]), {"web", "api", "api-migration", "api-bootstrap", "postgres"})
                self.assertEqual(set(config["networks"]), {"application", "database"})
                self.assertEqual(set(config["volumes"]), {"postgres-data"})
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                for resources in config.values():
                    for resource in resources.values():
                        self.assertEqual(resource, {"labels": expected})

    def test_observability_fixture_preserves_status_authority_and_shared_image_identity(self):
        value = source("observability")
        compose = value.split("\ncompose=(", 1)[1].split("\n)", 1)[0]
        self.assertEqual(compose.count("-f "), 1)
        self.assertIn('-f "$fixture_compose_file"', compose)
        self.assertIn('fixture_compose_file="$fixture_root/compose.prod.yaml"', value)
        self.assertIn('"$fixture_root/scripts/production-status.sh"', function(value, "collect_snapshot"))
        self.assertIn('config --no-interpolate --format json > "$fixture_compose_file"', value)
        self.assertIn('if source != fixture:', value)
        required = value.split("\n  required)", 1)[1].split("\n    ;;", 1)[0]
        self.assertEqual(required.count("test_image_artifact.py\" consume"), 2)
        self.assertNotIn("docker_labels", required)
        self.assertNotIn("build", required)
        disabled = value.split("\n  disabled)", 1)[1].split("\n    ;;", 1)[0]
        self.assertEqual(disabled.count('"${docker_labels[@]}"'), 2)
        self.assertEqual(disabled.count("--progress plain --no-cache --pull"), 2)
        copier = re.search(r'python3 -B - "\$ROOT_DIR" "\$fixture_root" <<\'PY\'\n(.*?)\nPY', value, re.S)
        self.assertIsNotNone(copier)
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture-repo"
            result = subprocess.run([sys.executable, "-B", "-", str(ROOT), str(fixture)],
                                    input=copier.group(1), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = sorted(path.relative_to(fixture) for path in fixture.rglob("*") if path.is_file())
            self.assertEqual(files, sorted(map(Path, ("scripts/production-status.sh",
                                                    "scripts/status_tools/production_status.py",
                                                    "scripts/backup_tools/backup_artifact.py"))))
            for relative in files:
                self.assertEqual((fixture / relative).read_bytes(), (ROOT / relative).read_bytes())
            collector = (fixture / "scripts/status_tools/production_status.py").read_text(encoding="utf-8")
            self.assertIn('config_files == {self.compose_file}', collector)
            self.assertIn('canonical_compose == canonical_repo / "compose.prod.yaml"', collector)

    def test_observability_fixture_rejects_render_or_label_drift_without_fallback(self):
        value = source("observability")
        checker = re.search(r'python3 -B - "\$status_root" "\$\{cleanup_labels\[@\]\}" <<\'PY\'\n(.*?)\nPY', value, re.S)
        self.assertIsNotNone(checker)
        config = {group: {"synthetic": {"labels": {"expected": "label"}}}
                  for group in ("services", "networks", "volumes")}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for mode in ("exact", "render-drift", "label-drift"):
                baseline = json.loads(json.dumps(config))
                fixture = json.loads(json.dumps(config))
                if mode == "render-drift":
                    fixture["services"]["synthetic"]["image"] = "synthetic-sensitive-value"
                elif mode == "label-drift":
                    baseline["volumes"]["synthetic"]["labels"] = {"wrong": "synthetic-sensitive-value"}
                    fixture = baseline
                (root / "source-compose.json").write_text(json.dumps(baseline), encoding="utf-8")
                (root / "fixture-compose.json").write_text(json.dumps(fixture), encoding="utf-8")
                with self.subTest(mode=mode):
                    result = subprocess.run([sys.executable, "-B", "-", str(root), "expected=label"],
                                            input=checker.group(1), capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0 if mode == "exact" else 1)
                    self.assertEqual(result.stdout, "")
                    self.assertNotIn("synthetic-sensitive-value", result.stderr)

    def test_backup_exit_trap_preserves_failure_and_propagates_cleanup_failure(self):
        cleanup = function(source("backup-restore"), "cleanup")
        for original, cleanup_result, expected in ((0, 0, 0), (0, 9, 1), (37, 0, 37), (37, 9, 37)):
            harness = "set -euo pipefail\ncleanup_complete=false\n" + cleanup
            harness += f'\ncleanup_resources() {{ printf "cleanup-called\\n"; return {cleanup_result}; }}\n'
            harness += f"trap cleanup EXIT\nexit {original}\n"
            with self.subTest(original=original, cleanup=cleanup_result):
                result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected)
                self.assertEqual(result.stdout, "cleanup-called\n")

    def test_observability_polling_and_fresh_recovery_remain_independent_proofs(self):
        observability = source("observability")
        polls = re.findall(r"^wait_for_snapshot ([a-z-]+) ([0-9]+)$", observability, re.M)
        self.assertEqual(polls, [("base", "30"), ("occurrence", "30"), ("rule-failure", "30"),
                                 ("unreachable", "15"), ("reset", "15")])
        for token in ("export OUR_LEDGER_RECURRING_POLL_DELAY_MS=10000",
                      "export OUR_LEDGER_RECURRING_INITIAL_DELAY_MS=60000",
                      "--force-recreate api", "sleep 1", '"$backup_after" != "$backup_before"'):
            self.assertIn(token, observability)
        fresh = source("fresh-host-bootstrap")
        self.assertEqual(fresh.count("    run_fresh_bootstrap("), 2)
        self.assertIn("result = run_fresh_bootstrap(", fresh)
        for token in ("crash_hook=crash_after_migration", 'pending["phase"] != "MIGRATION_VERIFIED"',
                      'if os.path.lexists(input_file)', 'if not adapter.household_bootstrap_is_exact()',
                      'inventory["lastSuccessValid"]', 'state["status"] != "READY"',
                      'adapter.read_schema_authority() != before'):
            self.assertIn(token, fresh)


if __name__ == "__main__":
    unittest.main()
