"""Tests for the GitLab git provider."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.git.protocol import RepoRef
from ai_portal.workers.git.providers.github import DefaultBranchPushBlocked
from ai_portal.workers.git.providers.gitlab import GitLabProvider


REPO = RepoRef(
    "acme/api", "main", "https://gitlab.com/acme/api.git"
)
PROJ = "acme%2Fapi"


@pytest.mark.asyncio
async def test_create_pr_draft_returns_merge_request() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            f"https://gitlab.com/api/v4/projects/{PROJ}/merge_requests"
        ).mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 100,
                    "iid": 5,
                    "web_url": "https://gitlab.com/acme/api/-/merge_requests/5",
                    "state": "opened",
                    "draft": True,
                    "source_branch": "worker/x",
                    "target_branch": "main",
                    "title": "Draft: fix",
                    "description": "",
                },
            )
        )
        p = GitLabProvider(token="t")
        pr = await p.create_pr(
            REPO, head="worker/x", base="main", title="fix", body="", draft=True
        )
    assert pr.number == 5
    assert pr.state == "draft"


@pytest.mark.asyncio
async def test_create_pr_blocks_default_head() -> None:
    p = GitLabProvider(token="t")
    with pytest.raises(DefaultBranchPushBlocked):
        await p.create_pr(REPO, head="main", base="main", title="x", body="")


@pytest.mark.asyncio
async def test_comment_posts_to_notes_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            f"https://gitlab.com/api/v4/projects/{PROJ}/merge_requests/5/notes"
        ).mock(return_value=httpx.Response(201, json={"id": 1}))
        p = GitLabProvider(token="t")
        await p.comment_pr(REPO, 5, "ok")


def test_parse_pr_event_open() -> None:
    p = GitLabProvider(token="t")
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {"iid": 9, "action": "open"},
        "project": {
            "path_with_namespace": "acme/api",
            "default_branch": "main",
            "git_http_url": "https://gitlab.com/acme/api.git",
        },
        "user": {"username": "alice"},
    }
    ev = p.parse_pr_event(payload, headers={})
    assert ev is not None
    assert ev.kind == "opened"
    assert ev.pr_number == 9
    assert ev.actor == "alice"


def test_parse_pr_event_rejects_bad_token() -> None:
    p = GitLabProvider(token="t", webhook_secret="shh")
    assert p.parse_pr_event({}, headers={"X-Gitlab-Token": "wrong"}) is None
