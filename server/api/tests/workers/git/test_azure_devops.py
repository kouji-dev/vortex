"""Tests for the Azure DevOps git provider."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.git.protocol import RepoRef
from ai_portal.workers.git.providers.azure_devops import AzureDevOpsProvider
from ai_portal.workers.git.providers.github import DefaultBranchPushBlocked


REPO = RepoRef(
    "acme/proj/repo", "main", "https://dev.azure.com/acme/proj/_git/repo"
)
PATH = "https://dev.azure.com/acme/proj/_apis/git/repositories/repo"


def _pr_body() -> dict:
    return {
        "pullRequestId": 33,
        "url": f"{PATH}/pullrequests/33",
        "status": "active",
        "isDraft": True,
        "sourceRefName": "refs/heads/worker/x",
        "targetRefName": "refs/heads/main",
        "title": "fix",
        "description": "",
    }


@pytest.mark.asyncio
async def test_create_pr_draft() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{PATH}/pullrequests?api-version=7.1").mock(
            return_value=httpx.Response(201, json=_pr_body())
        )
        p = AzureDevOpsProvider(pat="pat")
        pr = await p.create_pr(
            REPO, head="worker/x", base="main", title="fix", body="", draft=True
        )
    assert pr.number == 33
    assert pr.state == "draft"
    assert pr.head_branch == "worker/x"


@pytest.mark.asyncio
async def test_create_pr_blocks_default_head() -> None:
    p = AzureDevOpsProvider(pat="pat")
    with pytest.raises(DefaultBranchPushBlocked):
        await p.create_pr(REPO, head="main", base="main", title="x", body="")


@pytest.mark.asyncio
async def test_read_pr_parses_response() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{PATH}/pullrequests/33?api-version=7.1").mock(
            return_value=httpx.Response(200, json=_pr_body())
        )
        p = AzureDevOpsProvider(pat="pat")
        pr = await p.read_pr(REPO, 33)
    assert pr.head_branch == "worker/x"
    assert pr.base_branch == "main"


def test_parse_pr_event_created() -> None:
    p = AzureDevOpsProvider(pat="pat")
    payload = {
        "eventType": "git.pullrequest.created",
        "resource": {
            "pullRequestId": 33,
            "createdBy": {"uniqueName": "alice@x.com"},
            "repository": {
                "name": "repo",
                "defaultBranch": "refs/heads/main",
                "remoteUrl": "https://dev.azure.com/acme/proj/_git/repo",
                "project": {"organization": "acme", "name": "proj"},
            },
        },
    }
    ev = p.parse_pr_event(payload, headers={})
    assert ev is not None
    assert ev.kind == "opened"
    assert ev.pr_number == 33
    assert ev.actor == "alice@x.com"
