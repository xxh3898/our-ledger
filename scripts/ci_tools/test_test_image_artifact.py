from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from scripts.ci_tools import test_image_artifact as artifact
from scripts.ci_tools.test_change_classifier import job_block


HEAD = "a" * 40
TREE = "b" * 40
PR_HEAD = "c" * 40
PR_BASE = "d" * 40
PUSH = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": artifact.REPOSITORY,
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_REF": "refs/heads/dev",
    "GITHUB_WORKFLOW_REF": f"{artifact.REPOSITORY}/.github/workflows/full-ci.yml@refs/heads/dev",
    "GITHUB_RUN_ID": "34422287994",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_SHA": HEAD,
    "CI_PR_HEAD_SHA": "",
    "CI_PR_BASE_SHA": "",
    "CI_DOCKER_CACHE_MODE": "gha-write",
    "GITHUB_JOB": "test-images",
}
PR = {
    **PUSH,
    "GITHUB_EVENT_NAME": "pull_request",
    "GITHUB_BASE_REF": "dev",
    "GITHUB_REF": "refs/pull/154/merge",
    "GITHUB_WORKFLOW_REF": f"{artifact.REPOSITORY}/.github/workflows/full-ci.yml@refs/pull/154/merge",
    "GITHUB_SHA": HEAD,
    "CI_PR_HEAD_SHA": PR_HEAD,
    "CI_PR_BASE_SHA": PR_BASE,
    "CI_DOCKER_CACHE_MODE": "gha-read",
}


def identity(family: str = "api", environment: dict[str, str] | None = None) -> artifact.Authority:
    with patch.object(artifact, "_git", side_effect=lambda _root, rev: HEAD if rev == "HEAD" else TREE):
        return artifact.authority(family, environment or PR)


def docker_config(authority: artifact.Authority) -> bytes:
    value = {
        "architecture": "amd64",
        "os": "linux",
        "config": {"Labels": artifact.expected_labels(authority)},
        "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "f" * 64]},
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def write_archive(directory: Path, authority: artifact.Authority, *, member_name: str | None = None) -> tuple[Path, str]:
    config = docker_config(authority)
    image_id = "sha256:" + hashlib.sha256(config).hexdigest()
    config_name = image_id.removeprefix("sha256:") + ".json"
    layer_name = member_name or "fixture/layer.tar"
    embedded = [{
        "Config": config_name,
        "RepoTags": [artifact.canonical_reference(authority.family, authority.checkout_sha)],
        "Layers": [layer_name],
    }]
    archive = directory / artifact.ARCHIVE_NAME
    with archive.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as saved:
                for name, payload in (
                    (config_name, config),
                    (layer_name, b"synthetic-layer"),
                    ("manifest.json", json.dumps(embedded, separators=(",", ":")).encode()),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = 0o600
                    info.mtime = 0
                    saved.addfile(info, io.BytesIO(payload))
    return archive, image_id


def write_authority(directory: Path, identity_value: artifact.Authority) -> tuple[dict, Path]:
    archive, image_id = write_archive(directory, identity_value)
    size, archive_hash = artifact._hash_file(archive)
    value = artifact.manifest(identity_value, archive_size=size, archive_sha256=archive_hash, image_id=image_id)
    artifact._write_manifest(directory / artifact.MANIFEST_NAME, value)
    return value, archive


def mutate_archive_member(archive: Path, mutation: str) -> None:
    with tarfile.open(archive, mode="r:gz") as source:
        members = []
        for member in source.getmembers():
            payload = source.extractfile(member).read() if member.isfile() else None
            members.append((copy.copy(member), payload))
    with archive.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as destination:
                for member, payload in members:
                    destination.addfile(member, io.BytesIO(payload) if payload is not None else None)
                if mutation == "duplicate":
                    member, payload = members[0]
                    destination.addfile(copy.copy(member), io.BytesIO(payload))
                elif mutation == "symlink":
                    linked = tarfile.TarInfo("foreign-link")
                    linked.type = tarfile.SYMTYPE
                    linked.linkname = "../escape"
                    destination.addfile(linked)
                else:
                    raise AssertionError(mutation)


class AuthorityTest(unittest.TestCase):
    def test_actual_checkout_is_authority_and_pr_head_is_audit_metadata(self):
        value = identity()
        self.assertEqual(value.checkout_sha, HEAD)
        self.assertEqual(value.source_tree_sha, TREE)
        self.assertEqual(value.github_sha, HEAD)
        self.assertEqual(value.pr_head_sha, PR_HEAD)
        self.assertNotEqual(value.checkout_sha, value.pr_head_sha)

    def test_foreign_stale_or_unsupported_workflow_authority_is_rejected(self):
        changes = (
            {"GITHUB_REPOSITORY": "foreign/our-ledger"},
            {"GITHUB_RUN_ID": "0"},
            {"GITHUB_RUN_ATTEMPT": ""},
            {"GITHUB_SHA": "main"},
            {"CI_PR_HEAD_SHA": ""},
            {"GITHUB_EVENT_NAME": "workflow_call"},
            {"GITHUB_WORKFLOW_REF": f"{artifact.REPOSITORY}/.github/workflows/deploy.yml@refs/heads/main"},
            {"CI_DOCKER_CACHE_MODE": "gha-write"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(artifact.ArtifactError):
                identity(environment={**PR, **change})
        for family in ("runtime-config", "future", ""):
            with self.subTest(family=family), self.assertRaises(artifact.ArtifactError):
                identity(family)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="our-ledger-image-artifact-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.identity = identity()
        self.value, self.archive = write_authority(self.directory, self.identity)

    def rewrite(self, value: object, *, raw: bytes | None = None) -> None:
        destination = self.directory / artifact.MANIFEST_NAME
        destination.write_bytes(raw if raw is not None else json.dumps(value, separators=(",", ":")).encode())

    def validate(self) -> str:
        value = artifact._load_strict_json(self.directory / artifact.MANIFEST_NAME)
        image_id, config_digest = artifact.validate_manifest(value, self.identity, self.archive)
        artifact._validate_docker_archive(self.archive, value["imageReference"], image_id, config_digest)
        return image_id

    def test_valid_manifest_binds_archive_and_docker_save_config(self):
        self.assertRegex(self.validate(), r"^sha256:[0-9a-f]{64}$")

    def test_every_source_family_platform_and_runtime_authority_mismatch_is_rejected(self):
        changes = {
            "repository": "foreign/our-ledger",
            "workflowRef": "foreign-workflow",
            "workflowRunId": "999",
            "runAttempt": 2,
            "eventName": "push",
            "githubSha": "1" * 40,
            "prHeadSha": "2" * 40,
            "prBaseSha": "3" * 40,
            "checkoutSha": "4" * 40,
            "sourceTreeSha": "5" * 40,
            "imageFamily": "web",
            "platform": "linux/arm64",
            "dockerfilePath": "infra/docker/web.Dockerfile",
            "dockerfileSha256": "6" * 64,
            "dockerignorePath": ".dockerignore",
            "dockerignoreSha256": "7" * 64,
            "archiveName": "foreign.tar.gz",
            "ociSource": "https://example.invalid/foreign",
            "ociRevision": "8" * 40,
            "ociVersion": "9" * 40,
            "cacheMode": "gha-write",
            "producerJob": "foreign",
            "artifactFormat": "oci",
        }
        for key, changed in changes.items():
            value = {**self.value, key: changed}
            self.rewrite(value)
            with self.subTest(key=key), self.assertRaises(artifact.ArtifactError):
                self.validate()
            self.rewrite(self.value)

    def test_corrupt_replaced_or_wrong_hash_archive_is_rejected(self):
        for mutation in (b"corrupt", self.archive.read_bytes()[:-7], self.archive.read_bytes() + b"foreign"):
            original = self.archive.read_bytes()
            self.archive.write_bytes(mutation)
            with self.subTest(size=len(mutation)), self.assertRaises(artifact.ArtifactError):
                self.validate()
            self.archive.write_bytes(original)
        value = {**self.value, "archiveSha256": "0" * 64}
        self.rewrite(value)
        with self.assertRaises(artifact.ArtifactError):
            self.validate()

    def test_wrong_image_id_and_family_swap_in_archive_are_rejected(self):
        value = {**self.value, "imageId": "sha256:" + "0" * 64}
        self.rewrite(value)
        with self.assertRaises(artifact.ArtifactError):
            self.validate()
        self.rewrite({**self.value, "imageConfigDigest": "sha256:" + "1" * 64})
        with self.assertRaises(artifact.ArtifactError):
            self.validate()
        self.rewrite(self.value)
        web = identity("web")
        self.archive.unlink()
        write_archive(self.directory, web)
        size, digest = artifact._hash_file(self.archive)
        swapped = {**self.value, "archiveSize": size, "archiveSha256": digest}
        self.rewrite(swapped)
        with self.assertRaises(artifact.ArtifactError):
            self.validate()

    def test_path_traversal_link_duplicate_and_extra_archive_members_are_rejected(self):
        for unsafe in ("../escape/layer.tar", "/absolute/layer.tar", "bad\\layer.tar"):
            self.archive.unlink()
            write_archive(self.directory, self.identity, member_name=unsafe)
            size, digest = artifact._hash_file(self.archive)
            self.rewrite({**self.value, "archiveSize": size, "archiveSha256": digest})
            with self.subTest(unsafe=unsafe), self.assertRaises(artifact.ArtifactError):
                self.validate()
        for mutation in ("duplicate", "symlink"):
            self.archive.unlink()
            self.value, self.archive = write_authority(self.directory, self.identity)
            mutate_archive_member(self.archive, mutation)
            size, digest = artifact._hash_file(self.archive)
            self.rewrite({**self.value, "archiveSize": size, "archiveSha256": digest})
            with self.subTest(mutation=mutation), self.assertRaises(artifact.ArtifactError):
                self.validate()

    def test_malformed_duplicate_extra_and_wrong_scalar_manifest_is_rejected(self):
        malformed = (
            b"{",
            b'{' + b'"formatVersion":1,' * 2 + b'"x":1}',
            json.dumps({**self.value, "extra": True}).encode(),
            json.dumps({**self.value, "formatVersion": True}).encode(),
            json.dumps({**self.value, "archiveSize": "1"}).encode(),
            b"\xff",
        )
        for raw in malformed:
            self.rewrite({}, raw=raw)
            with self.subTest(raw=raw[:20]), self.assertRaises(artifact.ArtifactError):
                self.validate()

    def test_directory_requires_exact_two_regular_files(self):
        artifact._validate_artifact_directory(self.directory)
        extra = self.directory / "extra"
        extra.write_text("foreign", encoding="utf-8")
        with self.assertRaises(artifact.ArtifactError):
            artifact._validate_artifact_directory(self.directory)
        extra.unlink()
        manifest = self.directory / artifact.MANIFEST_NAME
        manifest.unlink()
        with self.assertRaises(artifact.ArtifactError):
            artifact._validate_artifact_directory(self.directory)
        manifest.symlink_to(self.archive)
        with self.assertRaises(artifact.ArtifactError):
            artifact._validate_artifact_directory(self.directory)


class AdoptionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="our-ledger-image-adopt-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.identity = identity()
        self.value, _ = write_authority(self.directory, self.identity)
        self.inspection = {
            "Id": self.value["imageId"],
            "Os": "linux",
            "Architecture": "amd64",
            "Config": {"Labels": artifact.expected_labels(self.identity)},
        }
        self.environment = {**PR, "GITHUB_JOB": "backup-restore"}

    def test_valid_consumer_loads_then_verifies_and_retags_exact_image(self):
        with patch.object(artifact, "_git", side_effect=lambda _root, rev: HEAD if rev == "HEAD" else TREE), \
             patch.object(artifact, "_image_exists", return_value=False), \
             patch.object(artifact, "_load_image") as load, \
             patch.object(artifact, "_inspect", return_value=self.inspection) as inspect, \
             patch.object(artifact, "_remove_image") as remove, \
             patch.object(artifact.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            artifact.consume("api", self.directory, "our-ledger-api:consumer", self.environment)
        load.assert_called_once()
        self.assertEqual(inspect.call_count, 2)
        self.assertIn(call(["docker", "image", "tag", self.value["imageReference"], "our-ledger-api:consumer"],
                           env=self.environment, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30), run.call_args_list)
        remove.assert_called_once_with(self.value["imageReference"], self.environment, required=True)

    def test_wrong_loaded_digest_or_oci_revision_fails_without_rebuild(self):
        cases = [
            {**self.inspection, "Id": "sha256:" + "0" * 64},
            {**self.inspection, "Config": {"Labels": {**self.inspection["Config"]["Labels"],
                                                       "org.opencontainers.image.revision": "0" * 40}}},
        ]
        for inspection in cases:
            with self.subTest(inspection=inspection["Id"]), \
                 patch.object(artifact, "_git", side_effect=lambda _root, rev: HEAD if rev == "HEAD" else TREE), \
                 patch.object(artifact, "_image_exists", return_value=False), \
                 patch.object(artifact, "_load_image") as load, \
                 patch.object(artifact, "_inspect", return_value=inspection), \
                 patch.object(artifact, "_remove_image") as remove, \
                 patch.object(artifact.docker_cache, "build_image") as build:
                with self.assertRaises(artifact.ArtifactError):
                    artifact.consume("api", self.directory, "our-ledger-api:consumer", self.environment)
            load.assert_called_once()
            build.assert_not_called()
            remove.assert_called_once_with(self.value["imageReference"], self.environment, required=False)

    def test_failed_post_tag_validation_removes_both_exact_tags(self):
        wrong_target = {**self.inspection, "Id": "sha256:" + "0" * 64}
        with patch.object(artifact, "_git", side_effect=lambda _root, rev: HEAD if rev == "HEAD" else TREE), \
             patch.object(artifact, "_image_exists", return_value=False), \
             patch.object(artifact, "_load_image"), \
             patch.object(artifact, "_inspect", side_effect=[self.inspection, wrong_target]), \
             patch.object(artifact, "_remove_image") as remove, \
             patch.object(artifact.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(artifact.docker_cache, "build_image") as build, \
             self.assertRaises(artifact.ArtifactError):
            artifact.consume("api", self.directory, "our-ledger-api:consumer", self.environment)
        build.assert_not_called()
        self.assertEqual(
            remove.call_args_list,
            [call(self.value["imageReference"], self.environment, required=False),
             call("our-ledger-api:consumer", self.environment, required=False)],
        )

    def test_wrong_consumer_family_tag_or_job_is_rejected_before_load(self):
        for family, target, job in (("web", "our-ledger-web:test", "backup-restore"),
                                    ("api", "--foreign", "backup-restore"),
                                    ("api", "our-ledger-api:test", "production-runtime")):
            with self.subTest(family=family, target=target, job=job), \
                 patch.object(artifact, "_git", side_effect=lambda _root, rev: HEAD if rev == "HEAD" else TREE), \
                 patch.object(artifact, "_load_image") as load, self.assertRaises(artifact.ArtifactError):
                artifact.consume(family, self.directory, target, {**PR, "GITHUB_JOB": job})
            load.assert_not_called()


class WorkflowContractTest(unittest.TestCase):
    def test_matrix_producer_is_full_direct_dev_only_and_uses_exact_pinned_actions(self):
        workflow = (artifact.ROOT / ".github/workflows/full-ci.yml").read_text(encoding="utf-8")
        producer = job_block(workflow, "test-images")
        self.assertIn("needs.repository.outputs.run_full != 'false'", producer)
        self.assertIn("needs.repository.outputs.docker_cache_mode != 'disabled'", producer)
        self.assertIn("family:\n          - api\n          - web", producer)
        self.assertIn("test_image_artifact.py produce", producer)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", producer)
        self.assertIn("name: our-ledger-test-image-${{ matrix.family }}-${{ github.run_attempt }}", producer)
        self.assertIn("retention-days: 1", producer)
        self.assertIn("compression-level: 0", producer)
        self.assertIn("if-no-files-found: error", producer)
        self.assertNotIn("github-token:", producer)
        self.assertNotIn("run-id:", producer)
        self.assertNotIn("repository:", producer)

    def test_consumers_download_only_named_current_run_artifacts_and_never_fallback_in_shared_mode(self):
        workflow = (artifact.ROOT / ".github/workflows/full-ci.yml").read_text(encoding="utf-8")
        expected = {
            "production-bootstrap": ("verify-production-bootstrap.sh", ("api",)),
            "fresh-host-bootstrap": ("verify-fresh-host-bootstrap.sh", ("api", "web")),
            "backup-restore": ("verify-backup-restore.sh", ("api",)),
            "observability": ("verify-observability.sh", ("api", "web")),
        }
        for name, (script, families) in expected.items():
            body = job_block(workflow, name)
            downloads = len(families)
            with self.subTest(name=name):
                self.assertEqual(
                    body.count("actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"),
                    downloads,
                )
                self.assertEqual(body.count("-${{ github.run_attempt }}"), downloads)
                self.assertIn("CI_TEST_IMAGE_MODE", body)
                self.assertIn("      - test-images", body)
                job_level = body.split("    steps:\n", 1)[0]
                self.assertNotIn("runner.temp", job_level)
                verification_step = body.rsplit("      - name:", 1)[-1]
                self.assertIn(f"run: ./scripts/{script}", verification_step)
                for family in families:
                    variable = f"CI_TEST_IMAGE_{family.upper()}_DIR"
                    directory = f"${{{{ runner.temp }}}}/our-ledger-test-image-{family}"
                    self.assertEqual(body.count(f"path: {directory}"), 1)
                    self.assertEqual(verification_step.count(f"{variable}: {directory}"), 1)
                for forbidden in ("github-token:", "repository:", "run-id:", "pattern:", "merge-multiple:"):
                    self.assertNotIn(forbidden, body)
            verifier = (artifact.ROOT / f"scripts/verify-{name}.sh").read_text(encoding="utf-8")
            self.assertIn('case "${CI_TEST_IMAGE_MODE:-disabled}" in', verifier)
            self.assertIn("required)", verifier)
            self.assertIn("disabled)", verifier)
            self.assertIn("알 수 없는 shared test image mode", verifier)
            self.assertNotIn("CI_TEST_IMAGE_MODE:-required", verifier)

    def test_main_release_clean_and_runtime_config_authorities_are_not_changed_by_shared_transport(self):
        workflow = (artifact.ROOT / ".github/workflows/full-ci.yml").read_text(encoding="utf-8")
        for name in ("production-runtime", "runtime-config-evolution", "release-transport"):
            body = job_block(workflow, name)
            self.assertNotIn("test-images", body)
            self.assertNotIn("test_image_artifact", body)
            self.assertNotIn("download-artifact", body)
        for filename in ("deploy.yml", "publish-release.yml"):
            source = (artifact.ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
            self.assertNotIn("our-ledger-test-image", source)
            self.assertNotIn("test_image_artifact", source)

    def test_shared_full_count_is_seven_and_six_consumer_builds_are_removed(self):
        # 2 strongest-clean + 2 producer + 3 runtime-config; shared consumers run zero builds.
        self.assertEqual(2 + len(artifact.CONSUMERS) + 3, 7)
        self.assertEqual(sum(len(consumers) for consumers in artifact.CONSUMERS.values()), 6)


class ProducerTest(unittest.TestCase):
    def test_producer_builds_canonical_labeled_image_with_cache_and_cleans_it(self):
        value = identity(environment=PUSH)
        config = docker_config(value)
        image_id = "sha256:" + hashlib.sha256(config).hexdigest()
        inspection = {"Id": image_id, "Os": "linux", "Architecture": "amd64",
                      "Config": {"Labels": artifact.expected_labels(value)}}
        with tempfile.TemporaryDirectory(prefix="our-ledger-image-produce-") as temporary:
            directory = Path(temporary) / "artifact"

            def save(_reference, destination, _environment):
                destination.parent.mkdir(parents=True, exist_ok=True)
                write_archive(destination.parent, value)

            with patch.object(artifact, "_git", side_effect=lambda _root, rev: HEAD if rev == "HEAD" else TREE), \
                 patch.object(artifact, "_image_exists", return_value=False), \
                 patch.object(artifact.docker_cache, "build_image", return_value=0) as build, \
                 patch.object(artifact, "_inspect", return_value=inspection), \
                 patch.object(artifact, "_save_image", side_effect=save), \
                 patch.object(artifact, "_remove_image") as remove:
                artifact.produce("api", directory, PUSH)
            arguments = build.call_args.args[1]
            self.assertIn("--pull", arguments)
            self.assertIn("linux/amd64", arguments)
            for key, expected in artifact.expected_labels(value).items():
                self.assertIn(f"{key}={expected}", arguments)
            remove.assert_called_once_with(artifact.canonical_reference("api", HEAD), PUSH, required=True)
            self.assertEqual({path.name for path in directory.iterdir()}, {artifact.ARCHIVE_NAME, artifact.MANIFEST_NAME})


if __name__ == "__main__":
    unittest.main()
