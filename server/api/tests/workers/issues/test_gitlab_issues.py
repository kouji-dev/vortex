"""Tests for the GitLab Issues tracker."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.issues.providers.gitlab_issues import (
    GitLabIssuesTracker,
)


PROJ = "acme%2Fapi"


@pytest.mark.asyncio
async def test_read_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get(f"https://gitlab.com/api/v4/projects/{PROJ}/issues/9").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "iid": 9,
                    "title": "T",
                    "description": "d",
                    "state": "opened",
                    "web_url": "https://gitlab.com/acme/api/issues/9",
                    "labels": ["worker"],
                },
            )
        )
        p = GitLabIssuesTracker(token="t")
        i = await p.read_issue(project="acme/api", external_id="9")
    assert i.external_id == "9"
    assert "worker" in i.labels


@pytest.mark.asyncio
async def test_comment_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            f"https://gitlab.com/api/v4/projects/{PROJ}/issues/9/notes"
        ).mock(return_value=httpx.Response(201, json={"id": 1}))
        p = GitLabIssuesTracker(token="t")
        await p.comment_issue(project="acme/api", external_id="9", body="hi")


def test_webhook_open_action_emits_created() -> None:
    p = GitLabIssuesTracker(token="t")
    ev = p.parse_webhook_event(
        payload={
            "object_kind": "issue",
            "object_attributes": {
                "id": 1,
                "iid": 9,
                "title": "T",
                "description": "d",
                "state": "opened",
                "action": "open",
                "labels": [{"title": "worker"}],
                "web_url": "u",
            },
            "project": {"path_with_namespace": "acme/api"},
            "user": {"username": "alice"},
        },
        headers={},
    )
    assert ev is not None
    assert ev.kind == "created"
    assert ev.actor == "alice"


def test_webhook_rejects_bad_token() -> None:
    p = GitLabIssuesTracker(token="t", webhook_secret="shh")
    assert (
        p.parse_webhook_event(
            payload={"object_kind": "issue"},
            headers={"X-Gitlab-Token": "wrong"},
        )
        is None
    )
