from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.release_tools import release_contract


ROOT = Path(__file__).resolve().parents[2]
DETECTOR = ROOT / "scripts" / "detect-runtime-config-change.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
FULL_CI_WORKFLOW = ROOT / ".github" / "workflows" / "full-ci.yml"
RUNTIME_DOCKERFILE = ROOT / "runtime-config.Dockerfile"
VERIFY_SCRIPT = ROOT / "scripts" / "verify-release-transport.sh"
REVISION = "1" * 40
API_DIGEST = "sha256:" + ("a" * 64)
WEB_DIGEST = "sha256:" + ("b" * 64)
RUNTIME_DIGEST = "sha256:" + ("c" * 64)
CHECKOUT_SHA = "d23441a48e516b6c34aea4fa41551a30e30af803"

RUNTIME_FILES = {
    "compose.prod.yaml": ("0600", "/runtime/compose.yaml"),
    "infra/nginx/nginx.conf": ("0600", "/runtime/infra/nginx/nginx.conf"),
    "scripts/backup-production.sh": ("0700", "/runtime/scripts/backup-production.sh"),
    "scripts/bootstrap-production.sh": (
        "0700",
        "/runtime/scripts/bootstrap-production.sh",
    ),
    "scripts/backup_tools/backup_artifact.py": (
        "0600",
        "/runtime/scripts/backup_tools/backup_artifact.py",
    ),
    "scripts/backup_tools/backup_core.sh": (
        "0600",
        "/runtime/scripts/backup_tools/backup_core.sh",
    ),
    "scripts/deploy-production.sh": (
        "0700",
        "/runtime/scripts/deploy-production.sh",
    ),
    "scripts/host_tools/deploy_transaction.py": (
        "0600",
        "/runtime/scripts/host_tools/deploy_transaction.py",
    ),
    "scripts/host_tools/fresh_bootstrap_state.py": (
        "0600",
        "/runtime/scripts/host_tools/fresh_bootstrap_state.py",
    ),
    "scripts/host_tools/fresh_host_bootstrap.py": (
        "0600",
        "/runtime/scripts/host_tools/fresh_host_bootstrap.py",
    ),
    "scripts/host_tools/host_state.py": (
        "0600",
        "/runtime/scripts/host_tools/host_state.py",
    ),
    "scripts/host_tools/production_deploy.py": (
        "0600",
        "/runtime/scripts/host_tools/production_deploy.py",
    ),
    "scripts/host_tools/production_fresh_bootstrap.py": (
        "0600",
        "/runtime/scripts/host_tools/production_fresh_bootstrap.py",
    ),
    "scripts/host_tools/production_host.py": (
        "0600",
        "/runtime/scripts/host_tools/production_host.py",
    ),
    "scripts/monitor-production.sh": ("0700", "/runtime/scripts/monitor-production.sh"),
    "scripts/production-status.sh": ("0700", "/runtime/scripts/production-status.sh"),
    "scripts/release_tools/release_contract.py": (
        "0700",
        "/runtime/scripts/release_tools/release_contract.py",
    ),
    "scripts/status_tools/monitor_policy.py": (
        "0600",
        "/runtime/scripts/status_tools/monitor_policy.py",
    ),
    "scripts/status_tools/monitor_worker.py": (
        "0600",
        "/runtime/scripts/status_tools/monitor_worker.py",
    ),
    "scripts/status_tools/production_status.py": (
        "0600",
        "/runtime/scripts/status_tools/production_status.py",
    ),
}
RUNTIME_SOURCES = set(RUNTIME_FILES)


class ReleaseContractTest(unittest.TestCase):
    def test_builds_and_parses_fixed_fresh_bootstrap_command(self) -> None:
        command = release_contract.build_bootstrap_command(
            revision=REVISION,
            runtime_config_digest=RUNTIME_DIGEST,
            actor="release_actor-1",
        )

        self.assertEqual(
            command,
            f"bootstrap-our-ledger-v1 {REVISION} {RUNTIME_DIGEST} release_actor-1",
        )
        self.assertEqual(
            release_contract.parse_bootstrap_command(command),
            {
                "actor": "release_actor-1",
                "revision": REVISION,
                "runtimeConfigDigest": RUNTIME_DIGEST,
            },
        )

    def test_fresh_bootstrap_command_rejects_flags_paths_and_extra_arguments(self) -> None:
        invalid = (
            f"bootstrap-our-ledger-v1 {REVISION} {RUNTIME_DIGEST} actor extra",
            f"bootstrap-our-ledger-v1 {REVISION} {RUNTIME_DIGEST} actor;id",
            f"bootstrap-our-ledger-v1 {REVISION} /tmp/runtime actor",
            f"bootstrap-our-ledger-v1 {REVISION} {RUNTIME_DIGEST} actor --skip-backup",
            f"bootstrap-our-ledger-v1 {'A' * 40} {RUNTIME_DIGEST} actor",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(release_contract.ContractError):
                    release_contract.parse_bootstrap_command(value)

    def test_builds_and_parses_fixed_keep_command(self) -> None:
        command = release_contract.build_command(
            revision=REVISION,
            mode="keep",
            actor="xxh3898",
        )

        self.assertEqual(
            command,
            f"deploy-our-ledger-v1 {REVISION} keep xxh3898",
        )
        self.assertEqual(
            release_contract.parse_command(command),
            {
                "actor": "xxh3898",
                "mode": "keep",
                "revision": REVISION,
                "runtimeConfigDigest": None,
            },
        )

    def test_builds_and_parses_fixed_update_command(self) -> None:
        command = release_contract.build_command(
            revision=REVISION,
            mode="update",
            runtime_config_digest=RUNTIME_DIGEST,
            actor="release_actor-1",
        )

        self.assertEqual(
            command,
            f"deploy-our-ledger-v1 {REVISION} update {RUNTIME_DIGEST} release_actor-1",
        )
        self.assertEqual(
            release_contract.parse_command(command)["runtimeConfigDigest"],
            RUNTIME_DIGEST,
        )

    def test_rejects_command_injection_and_extra_arguments(self) -> None:
        invalid_commands = (
            f"deploy-our-ledger-v1 {REVISION} keep actor extra",
            f"deploy-our-ledger-v1 {REVISION} keep actor;uname",
            f"deploy-our-ledger-v1 {REVISION} update {RUNTIME_DIGEST} actor --flag",
            f"deploy-our-ledger-v1 {REVISION} update /tmp/image actor",
            f"docker compose -f /tmp/compose.yaml up {REVISION}",
        )

        for command in invalid_commands:
            with self.subTest(command=command):
                with self.assertRaises(release_contract.ContractError):
                    release_contract.parse_command(command)

    def test_rejects_invalid_revision_digest_mode_and_actor(self) -> None:
        invalid_arguments = (
            {"revision": release_contract.ZERO_SHA, "mode": "keep", "actor": "actor"},
            {"revision": REVISION.upper().replace("1", "A"), "mode": "keep", "actor": "actor"},
            {"revision": REVISION, "mode": "other", "actor": "actor"},
            {"revision": REVISION, "mode": "keep", "actor": "actor name"},
            {
                "revision": REVISION,
                "mode": "update",
                "actor": "actor",
                "runtime_config_digest": "sha256:ABC",
            },
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(release_contract.ContractError):
                    release_contract.build_command(**arguments)

    def test_validates_publish_digest_set_for_keep_and_update(self) -> None:
        keep = release_contract.validate_publish_result(
            revision=REVISION,
            api_digest=API_DIGEST,
            web_digest=WEB_DIGEST,
            mode="keep",
            runtime_config_digest="",
        )
        update = release_contract.validate_publish_result(
            revision=REVISION,
            api_digest=API_DIGEST,
            web_digest=WEB_DIGEST,
            mode="update",
            runtime_config_digest=RUNTIME_DIGEST,
        )

        self.assertIsNone(keep["runtimeConfigDigest"])
        self.assertEqual(update["runtimeConfigDigest"], RUNTIME_DIGEST)

    def test_cli_failure_is_generic_and_does_not_echo_input(self) -> None:
        secret_like_actor = "actor;private-value"
        result = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/release_tools/release_contract.py"),
                "build-command",
                "--revision",
                REVISION,
                "--mode",
                "keep",
                "--actor",
                secret_like_actor,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "release contract validation failed\n")
        self.assertNotIn(secret_like_actor, result.stderr)


class RuntimeConfigChangeDetectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self._git("init", "--initial-branch=main")
        self._git("config", "user.name", "Release Test")
        self._git("config", "user.email", "release-test@example.test")
        self._write("README.md", "baseline\n")
        self._write("compose.prod.yaml", "services: {}\n")
        self.baseline = self._commit("baseline")
        self._write("README.md", "application-only\n")
        self.app_only = self._commit("application")
        self._write("compose.prod.yaml", "services:\n  web: {}\n")
        self.runtime_change = self._commit("runtime")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_app_only_change_keeps_runtime_config(self) -> None:
        result = self._detect(self.baseline, self.app_only, "false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "keep\n")

    def test_runtime_change_and_force_sync_update_runtime_config(self) -> None:
        changed = self._detect(self.app_only, self.runtime_change, "false")
        forced = self._detect(self.baseline, self.app_only, "true")

        self.assertEqual(changed.returncode, 0, changed.stderr)
        self.assertEqual(changed.stdout, "update\n")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual(forced.stdout, "update\n")

    def test_zero_baseline_is_bootstrap_update(self) -> None:
        result = self._detect(release_contract.ZERO_SHA, self.app_only, "false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "update\n")

    def test_invalid_or_missing_revision_fails_closed(self) -> None:
        results = (
            self._detect("a" * 39, self.app_only, "false"),
            self._detect("A" * 40, self.app_only, "false"),
            self._detect("f" * 40, self.app_only, "false"),
            self._detect(self.baseline, "f" * 40, "false"),
            self._detect(self.baseline, self.app_only, "yes"),
        )

        for result in results:
            with self.subTest(stderr=result.stderr):
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_non_ancestor_range_fails_closed(self) -> None:
        self._git("switch", "--detach", self.baseline)
        self._write("README.md", "sibling\n")
        sibling = self._commit("sibling")

        result = self._detect(self.app_only, sibling, "false")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("range is invalid", result.stderr)

    def _write(self, relative: str, value: str) -> None:
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")

    def _commit(self, message: str) -> str:
        self._git("add", ".")
        self._git("commit", "-m", message)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        )

    def _detect(
        self,
        before: str,
        after: str,
        force: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(DETECTOR), before, after, force],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )


class ReleaseSourceContractTest(unittest.TestCase):
    def test_full_ci_is_reusable_and_main_validation_has_one_authority(self) -> None:
        workflow = FULL_CI_WORKFLOW.read_text(encoding="utf-8")
        push_block = workflow[
            workflow.index("  push:\n") : workflow.index("  workflow_dispatch:\n")
        ]

        self.assertIn("  workflow_call:\n", workflow)
        self.assertIn("      - dev\n", push_block)
        self.assertNotIn("      - main\n", push_block)
        self.assertIn("  release-transport:\n", workflow)
        self.assertIn("run: ./scripts/verify-release-transport.sh", workflow)

    def test_deploy_workflow_is_inert_by_default_and_serialized(self) -> None:
        workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        publish = workflow_job(workflow, "publish")
        deploy = workflow_job(workflow, "deploy")

        self.assertIn("      - main\n", workflow)
        self.assertIn("  workflow_dispatch:\n", workflow)
        self.assertIn("  group: our-ledger-production\n", workflow)
        self.assertIn("  cancel-in-progress: false\n", workflow)
        self.assertIn("uses: ./.github/workflows/full-ci.yml", workflow)
        gate = "vars.OUR_LEDGER_DEPLOY_ENABLED == 'true'"
        self.assertIn(gate, publish)
        self.assertIn(gate, deploy)
        self.assertEqual(workflow.count(gate), 2)
        self.assertIn("github.ref == 'refs/heads/main'", publish)
        self.assertIn("github.ref == 'refs/heads/main'", deploy)

    def test_workflow_uses_exact_sha_arm64_images_labels_and_digests(self) -> None:
        workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        publish = workflow_job(workflow, "publish")

        self.assertIn("runs-on: ubuntu-24.04-arm", publish)
        self.assertEqual(publish.count("platforms: linux/arm64"), 3)
        self.assertEqual(publish.count("push: true"), 3)
        for image in (
            "ghcr.io/xxh3898/our-ledger-api",
            "ghcr.io/xxh3898/our-ledger-web",
            "ghcr.io/xxh3898/our-ledger-runtime-config",
        ):
            self.assertIn(image, workflow)
        self.assertIn("tags: ${{ env.API_IMAGE_NAME }}:${{ github.sha }}", publish)
        self.assertIn("tags: ${{ env.WEB_IMAGE_NAME }}:${{ github.sha }}", publish)
        self.assertIn(
            "tags: ${{ env.RUNTIME_CONFIG_IMAGE_NAME }}:${{ github.sha }}",
            publish,
        )
        self.assertGreaterEqual(
            publish.count("org.opencontainers.image.revision=${{ github.sha }}"),
            3,
        )
        self.assertGreaterEqual(
            publish.count("org.opencontainers.image.version=${{ github.sha }}"),
            3,
        )
        self.assertGreaterEqual(
            publish.count(
                "org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}"
            ),
            3,
        )
        self.assertIn("validate-publish", publish)
        self.assertNotRegex(workflow, r"(?i)ghcr\.io/[^\s]+:latest")

    def test_workflow_permissions_and_transport_boundary_are_minimal(self) -> None:
        workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        publish = workflow_job(workflow, "publish")
        deploy = workflow_job(workflow, "deploy")

        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("      contents: read", publish)
        self.assertIn("      deployments: read", publish)
        self.assertIn("      packages: write", publish)
        self.assertNotIn("id-token: write", publish)
        self.assertIn("      contents: read", deploy)
        self.assertIn("      packages: read", deploy)
        self.assertIn("      id-token: write", deploy)
        self.assertNotIn("packages: write", deploy)
        self.assertIn("tailscale/github-action@", deploy)
        self.assertIn("build-command", deploy)
        send_step = deploy[deploy.index("      - name: Send fixed deployment intent") :]
        command_build = send_step[
            send_step.index('deploy_command="$(') : send_step.index("          printf")
        ]
        ssh_invocation = send_step[send_step.index("| ssh") :]

        self.assertIn("printf '%s' \"${GHCR_TOKEN}\"", send_step)
        self.assertIn("\"${deploy_command}\"", ssh_invocation)
        self.assertNotIn("GHCR_TOKEN", command_build)
        self.assertNotIn("${GHCR_TOKEN}", ssh_invocation)

    def test_privileged_workflow_actions_use_exact_commit_revisions(self) -> None:
        workflow = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

        for job_id in ("publish", "deploy"):
            job = workflow_job(workflow, job_id)
            action_refs = re.findall(
                r"^\s+uses:\s+([^\s@]+)@([^\s#]+)",
                job,
                re.MULTILINE,
            )

            self.assertTrue(action_refs, job_id)
            self.assertIn(("actions/checkout", CHECKOUT_SHA), action_refs)
            for action, revision in action_refs:
                with self.subTest(job=job_id, action=action):
                    self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_runtime_config_dockerfile_has_exact_secret_free_source_allowlist(self) -> None:
        dockerfile = RUNTIME_DOCKERFILE.read_text(encoding="utf-8")
        copy_entries = re.findall(
            r"^COPY --chmod=([0-9]{4}) (\S+) (\S+)$",
            dockerfile,
            re.MULTILINE,
        )

        self.assertIn("FROM scratch", dockerfile)
        self.assertCountEqual(
            copy_entries,
            [
                (mode, source, destination)
                for source, (mode, destination) in RUNTIME_FILES.items()
            ],
        )
        self.assertEqual(len(copy_entries), len(RUNTIME_FILES))
        self.assertIn('org.opencontainers.image.revision="${REVISION}"', dockerfile)
        self.assertIn('org.opencontainers.image.version="${REVISION}"', dockerfile)
        self.assertIn(
            'org.opencontainers.image.source="https://github.com/xxh3898/our-ledger"',
            dockerfile,
        )
        self.assertIn('io.chochiho.runtime-config.project="our-ledger"', dockerfile)
        self.assertNotRegex(dockerfile, r"(?m)^COPY\s+(?:--\S+\s+)*\.\s")
        self.assertNotRegex(dockerfile, r"(?i)\.env|private|secret|\.pem|\.key")
        for source in RUNTIME_SOURCES:
            self.assertTrue((ROOT / source).is_file(), source)

    def test_detector_and_artifact_sources_stay_in_sync(self) -> None:
        detector = DETECTOR.read_text(encoding="utf-8")
        dockerfile = RUNTIME_DOCKERFILE.read_text(encoding="utf-8")

        for source in sorted(RUNTIME_SOURCES):
            self.assertIn(source, detector)
            self.assertIn(source, dockerfile)
        self.assertIn("runtime-config.Dockerfile", detector)

    def test_release_gate_uses_only_synthetic_local_boundaries(self) -> None:
        source = VERIFY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("python3 -m unittest", source)
        self.assertIn("--platform linux/arm64", source)
        self.assertIn("--network none", source)
        self.assertIn(
            "io.homeserver.cleanup.task=issue-43-host-deploy-transaction",
            source,
        )
        self.assertNotRegex(
            source,
            r"(?m)(?:^|\s)(?:curl|gh|ssh|tailscale)(?:\s|$)|docker\s+(?:login|push)",
        )


def workflow_job(workflow: str, job_id: str) -> str:
    header = f"\n  {job_id}:\n"
    start = workflow.find(header)
    if start < 0:
        raise AssertionError(f"missing workflow job: {job_id}")
    body_start = start + len(header)
    match = re.search(r"\n  [A-Za-z0-9_-]+:\n", workflow[body_start:])
    return workflow[start:] if match is None else workflow[start : body_start + match.start()]


if __name__ == "__main__":
    unittest.main()
