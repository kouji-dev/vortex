"""Tests for the Azure Boards tracker."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.issues.providers.azure_boards import (
    AzureBoardsTracker,
)


PROJ = "acme/proj"
BASE = f"https://dev.azure.com/{PROJ}/_apis/wit"


@pytest.mark.asyncio
async def test_read_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{BASE}/workitems/42?api-version=7.1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 42,
                    "url": f"{BASE}/workitems/42",
                    "fields": {
                        "System.Title": "Bug",
                        "System.Description": "details",
                        "System.State": "Active",
                        "System.Tags": "worker; bug",
                        "System.TeamProject": "proj",
                    },
                    "_links": {
                        "html": {
                            "href": "https://dev.azure.com/acme/proj/_workitems/edit/42"
                        }
                    },
                },
            )
        )
        p = AzureBoardsTracker(pat="pat")
        i = await p.read_issue(project=PROJ, external_id="42")
    assert i.external_id == "42"
    assert i.title == "Bug"
    assert "worker" in i.labels
    assert i.repo_hint == "proj"


@pytest.mark.asyncio
async def test_comment_posts_to_comments_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(
            f"{BASE}/workItems/42/comments?api-version=7.1-preview.3"
        ).mock(return_value=httpx.Response(201, json={"id": 1}))
        p = AzureBoardsTracker(pat="pat")
        await p.comment_issue(project=PROJ, external_id="42", body="hi")


@pytest.mark.asyncio
async def test_set_status_patches_state_field() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        route = mock.patch(f"{BASE}/workitems/42?api-version=7.1").mock(
            return_value=httpx.Response(200, json={})
        )
        p = AzureBoardsTracker(pat="pat")
        await p.set_status(project=PROJ, external_id="42", status="Done")
    sent = route.calls[0].request
    assert b"System.State" in sent.content
    assert b"Done" in sent.content


def test_webhook_workitem_created_emits_created() -> None:
    p = AzureBoardsTracker(pat="pat")
    ev = p.parse_webhook_event(
        payload={
            "eventType": "workitem.created",
            "resource": {
                "id": 42,
                "fields": {
                    "System.Title": "T",
                    "System.State": "New",
                    "System.TeamProject": "proj",
                    "System.Tags": "worker",
                },
                "_links": {"html": {"href": "url"}},
            },
            "createdBy": {"uniqueName": "alice@x.com"},
        },
        headers={},
    )
    assert ev is not None
    assert ev.kind == "created"
    assert ev.actor == "alice@x.com"
    assert "worker" in ev.issue.labels


def test_webhook_skips_non_workitem_event() -> None:
    p = AzureBoardsTracker(pat="pat")
    assert p.parse_webhook_event({"eventType": "git.push"}, headers={}) is None
