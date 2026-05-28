"""Tests for the Gitea git provider."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.git.protocol import RepoRef
from ai_portal.workers.git.providers.gitea import GiteaProvider
from ai_portal.workers.git.providers.github import DefaultBranchPushBlocked


BASE = "https://gitea.example.com"
REPO = RepoRef("acme/api", "main", f"{BASE}/acme/api.git")


def _pr_body() -> dict:
    return {
        "id": 1,
        "number": 7,
        "html_url": f"{BASE}/acme/api/pulls/7",
        "state": "open",
        "head": {"ref": "worker/x"},
        "base": {"ref": "main"},
        "title": "WIP: fix",
        "body": "",
    }


@pytest.mark.asyncio
async def test_create_pr_marks_wip_when_draft() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE}/api/v1/repos/acme/api/pulls").mock(
            return_value=httpx.Response(201, json=_pr_body())
        )
        p = GiteaProvider(token="t", base_url=BASE)
        pr = await p.create_pr(
            REPO, head="worker/x", base="main", title="fix", body="", draft=True
        )
    assert pr.number == 7
    assert pr.state == "draft"
    assert pr.title.startswith("WIP:")


@pytest.mark.asyncio
async def test_create_pr_blocks_default_head() -> None:
    p = GiteaProvider(token="t", base_url=BASE)
    with pytest.raises(DefaultBranchPushBlocked):
        await p.create_pr(REPO, head="main", base="main", title="x", body="")


@pytest.mark.asyncio
async def test_comment_pr_uses_issue_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE}/api/v1/repos/acme/api/issues/7/comments").mock(
            return_value=httpx.Response(201, json={"id": 1})
        )
        p = GiteaProvider(token="t", base_url=BASE)
        await p.comment_pr(REPO, 7, "ok")


def test_parse_pr_event_opened() -> None:
    p = GiteaProvider(token="t", base_url=BASE)
    payload = {
        "action": "opened",
        "pull_request": {"number": 11},
        "repository": {
            "full_name": "acme/api",
            "default_branch": "main",
            "clone_url": f"{BASE}/acme/api.git",
        },
        "sender": {"login": "bob"},
    }
    ev = p.parse_pr_event(payload, headers={})
    assert ev is not None
    assert ev.kind == "opened"
    assert ev.actor == "bob"
