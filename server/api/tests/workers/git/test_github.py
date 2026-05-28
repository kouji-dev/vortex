"""Tests for the GitHub git provider."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import respx

from ai_portal.workers.git.protocol import RepoRef
from ai_portal.workers.git.providers.github import (
    DefaultBranchPushBlocked,
    GitHubProvider,
)


REPO = RepoRef("acme/api", "main", "https://github.com/acme/api.git")


def _pr_body(number: int = 42, draft: bool = True) -> dict:
    return {
        "id": 1,
        "number": number,
        "html_url": f"https://github.com/acme/api/pull/{number}",
        "state": "open",
        "draft": draft,
        "head": {"ref": "worker/t-1"},
        "base": {"ref": "main"},
        "title": "fix",
        "body": "...",
    }


@pytest.mark.asyncio
async def test_create_pr_draft() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.github.com/repos/acme/api/pulls").mock(
            return_value=httpx.Response(201, json=_pr_body())
        )
        p = GitHubProvider(token="ghs_fake")
        pr = await p.create_pr(
            REPO,
            head="worker/t-1",
            base="main",
            title="fix",
            body="...",
            draft=True,
        )
    assert pr.number == 42
    assert pr.state == "draft"
    assert pr.head_branch == "worker/t-1"


@pytest.mark.asyncio
async def test_create_pr_blocks_default_branch_as_head() -> None:
    p = GitHubProvider(token="ghs_fake")
    with pytest.raises(DefaultBranchPushBlocked):
        await p.create_pr(
            REPO, head="main", base="main", title="x", body="y"
        )


@pytest.mark.asyncio
async def test_push_blocks_default_branches() -> None:
    p = GitHubProvider(token="ghs_fake")
    for branch in ("main", "master", "trunk", "develop"):
        with pytest.raises(DefaultBranchPushBlocked):
            await p.push(object(), branch=branch)


@pytest.mark.asyncio
async def test_push_calls_git_push_on_non_default() -> None:
    from unittest.mock import AsyncMock, MagicMock

    sp = MagicMock()
    sp.exec = AsyncMock(return_value=MagicMock(exit_code=0, stderr=""))
    sandbox = {"provider": sp, "handle": object()}
    p = GitHubProvider(token="ghs_fake")
    await p.push(sandbox, branch="worker/foo")
    cmd = sp.exec.call_args[0][1]
    assert cmd[:3] == ["git", "push", "-u"]
    assert cmd[-1] == "worker/foo"


@pytest.mark.asyncio
async def test_comment_pr_posts_to_issues_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            "https://api.github.com/repos/acme/api/issues/42/comments"
        ).mock(return_value=httpx.Response(201, json={"id": 1}))
        p = GitHubProvider(token="ghs_fake")
        await p.comment_pr(REPO, 42, "looks good")


@pytest.mark.asyncio
async def test_read_pr_parses_response() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.github.com/repos/acme/api/pulls/42").mock(
            return_value=httpx.Response(200, json=_pr_body(draft=False))
        )
        p = GitHubProvider(token="ghs_fake")
        pr = await p.read_pr(REPO, 42)
    assert pr.state == "open"
    assert pr.title == "fix"


@pytest.mark.asyncio
async def test_update_pr_patches_and_reads() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.patch("https://api.github.com/repos/acme/api/pulls/42").mock(
            return_value=httpx.Response(200, json=_pr_body())
        )
        mock.get("https://api.github.com/repos/acme/api/pulls/42").mock(
            return_value=httpx.Response(200, json=_pr_body(draft=False))
        )
        p = GitHubProvider(token="ghs_fake")
        pr = await p.update_pr(REPO, 42, title="new")
    assert pr.number == 42


def test_parse_pr_event_opened() -> None:
    p = GitHubProvider(token="t")
    payload = {
        "action": "opened",
        "pull_request": {"number": 7},
        "repository": {
            "full_name": "acme/api",
            "default_branch": "main",
            "clone_url": "https://github.com/acme/api.git",
        },
        "sender": {"login": "alice"},
    }
    ev = p.parse_pr_event(payload, headers={})
    assert ev is not None
    assert ev.kind == "opened"
    assert ev.pr_number == 7
    assert ev.actor == "alice"


def test_parse_pr_event_rejects_bad_signature() -> None:
    p = GitHubProvider(token="t", webhook_secret="shh")
    payload = {
        "action": "opened",
        "pull_request": {"number": 1},
        "repository": {
            "full_name": "acme/api",
            "default_branch": "main",
            "clone_url": "x",
        },
        "sender": {"login": "x"},
    }
    assert p.parse_pr_event(payload, headers={"X-Hub-Signature-256": "bad"}) is None


def test_parse_pr_event_accepts_valid_signature() -> None:
    payload = {
        "action": "opened",
        "pull_request": {"number": 1},
        "repository": {
            "full_name": "acme/api",
            "default_branch": "main",
            "clone_url": "x",
        },
        "sender": {"login": "alice"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()
    p = GitHubProvider(token="t", webhook_secret="shh")
    assert (
        p.parse_pr_event(payload, headers={"X-Hub-Signature-256": sig})
        is not None
    )


def test_parse_pr_event_returns_none_for_non_pr_payload() -> None:
    p = GitHubProvider(token="t")
    assert p.parse_pr_event({"action": "ping"}, headers={}) is None


def test_registry_register_and_get() -> None:
    from ai_portal.workers.git import registry

    registry.clear()
    p = GitHubProvider(token="t")
    registry.register(p)
    assert registry.get("github") is p
    assert "github" in registry.all_providers()
    registry.clear()
