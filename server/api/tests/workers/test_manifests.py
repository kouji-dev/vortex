"""Tests for the bundled provider manifests."""

from __future__ import annotations

from ai_portal.workers.git import manifests as git_m
from ai_portal.workers.issues import manifests as issue_m
from ai_portal.workers.sandboxes import manifests as sandbox_m
from ai_portal.workers.triggers import manifests as trigger_m
from ai_portal.workers.types import TriggerSourceKind


def test_sandbox_manifests_cover_all_providers() -> None:
    names = {m.name for m in sandbox_m.all_manifests()}
    assert {"fake", "docker", "kubernetes", "e2b", "daytona", "firecracker"} <= names


def test_git_manifests_cover_all_providers() -> None:
    names = {m.name for m in git_m.all_manifests()}
    assert {"github", "gitlab", "bitbucket", "gitea", "azure_devops"} == names


def test_issue_manifests_cover_all_providers() -> None:
    names = {m.name for m in issue_m.all_manifests()}
    assert {
        "jira_cloud",
        "linear",
        "github_issues",
        "gitlab_issues",
        "azure_boards",
    } == names


def test_trigger_manifests_cover_all_kinds() -> None:
    kinds = {m.kind for m in trigger_m.all_manifests()}
    assert set(TriggerSourceKind) == kinds


def test_sandbox_docker_manifest_marks_egress_supported() -> None:
    assert sandbox_m.get("docker").supports_egress_acl is True


def test_git_manifests_all_block_default_branch() -> None:
    for m in git_m.all_manifests():
        assert m.blocks_default_branch is True
