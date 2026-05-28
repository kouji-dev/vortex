"""Tests for the Bitbucket Cloud git provider."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.git.protocol import RepoRef
from ai_portal.workers.git.providers.bitbucket import BitbucketProvider
from ai_portal.workers.git.providers.github import DefaultBranchPushBlocked


REPO = RepoRef("acme/api", "main", "https://bitbucket.org/acme/api.git")


def _pr_body() -> dict:
    return {
        "id": 12,
        "links": {"html": {"href": "https://bitbucket.org/acme/api/pull-requests/12"}},
        "state": "OPEN",
        "source": {"branch": {"name": "worker/x"}},
        "destination": {"branch": {"name": "main"}},
        "title": "DRAFT: fix",
        "description": "",
    }


@pytest.mark.asyncio
async def test_create_pr() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            "https://api.bitbucket.org/2.0/repositories/acme/api/pullrequests"
        ).mock(return_value=httpx.Response(201, json=_pr_body()))
        p = BitbucketProvider(username="u", app_password="p")
        pr = await p.create_pr(
            REPO, head="worker/x", base="main", title="fix", body="", draft=True
        )
    assert pr.number == 12
    assert pr.state == "open"


@pytest.mark.asyncio
async def test_create_pr_blocks_default_head() -> None:
    p = BitbucketProvider(username="u", app_password="p")
    with pytest.raises(DefaultBranchPushBlocked):
        await p.create_pr(REPO, head="main", base="main", title="x", body="")


@pytest.mark.asyncio
async def test_comment_pr_uses_content_raw() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            "https://api.bitbucket.org/2.0/repositories/acme/api/pullrequests/12/comments"
        ).mock(return_value=httpx.Response(201, json={"id": 1}))
        p = BitbucketProvider(username="u", app_password="p")
        await p.comment_pr(REPO, 12, "lgtm")


def test_parse_pr_event_created() -> None:
    p = BitbucketProvider(username="u", app_password="p")
    payload = {
        "pullrequest": {"id": 12},
        "repository": {
            "full_name": "acme/api",
            "links": {"clone": [
                {"name": "https", "href": "https://bitbucket.org/acme/api.git"}
            ]},
        },
        "actor": {"username": "alice"},
    }
    ev = p.parse_pr_event(payload, headers={"X-Event-Key": "pullrequest:created"})
    assert ev is not None
    assert ev.kind == "opened"
    assert ev.pr_number == 12
