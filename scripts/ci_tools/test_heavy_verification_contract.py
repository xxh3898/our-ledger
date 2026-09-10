"""Deterministic contracts complement, but do not replace, Docker proofs."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
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
