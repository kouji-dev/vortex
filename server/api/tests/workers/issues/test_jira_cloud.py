"""Tests for the Jira Cloud tracker."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.issues.providers.jira_cloud import JiraCloudTracker


SITE = "https://acme.atlassian.net"


@pytest.mark.asyncio
async def test_read_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{SITE}/rest/api/3/issue/ENG-42").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "10042",
                    "key": "ENG-42",
                    "fields": {
                        "summary": "Fix bug",
                        "description": "details",
                        "status": {"name": "To Do"},
                        "labels": ["worker", "bug"],
                    },
                },
            )
        )
        p = JiraCloudTracker(site=SITE, email="u", token="t")
        issue = await p.read_issue(project="ENG", external_id="ENG-42")
    assert issue.title == "Fix bug"
    assert "worker" in issue.labels
    assert issue.url.endswith("/browse/ENG-42")


@pytest.mark.asyncio
async def test_comment_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{SITE}/rest/api/3/issue/ENG-1/comment").mock(
            return_value=httpx.Response(201, json={"id": "1"})
        )
        p = JiraCloudTracker(site=SITE, email="u", token="t")
        await p.comment_issue(project="ENG", external_id="ENG-1", body="hi")


@pytest.mark.asyncio
async def test_set_status_finds_and_posts_transition() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{SITE}/rest/api/3/issue/ENG-1/transitions").mock(
            return_value=httpx.Response(
                200,
                json={"transitions": [{"id": "11", "name": "In Progress"}]},
            )
        )
        mock.post(f"{SITE}/rest/api/3/issue/ENG-1/transitions").mock(
            return_value=httpx.Response(204)
        )
        p = JiraCloudTracker(site=SITE, email="u", token="t")
        await p.set_status(project="ENG", external_id="ENG-1", status="in progress")


def test_webhook_label_added_emits_labeled() -> None:
    p = JiraCloudTracker(site=SITE, email="u", token="t")
    evt = p.parse_webhook_event(
        payload={
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "id": "10",
                "key": "ENG-1",
                "fields": {
                    "summary": "s",
                    "description": "d",
                    "status": {"name": "Todo"},
                    "labels": ["worker"],
                },
            },
            "user": {"displayName": "Alice"},
            "changelog": {"items": [{"field": "labels", "toString": "worker"}]},
        },
        headers={},
    )
    assert evt is not None
    assert evt.kind == "labeled"
    assert evt.actor == "Alice"


def test_webhook_created_emits_created() -> None:
    p = JiraCloudTracker(site=SITE, email="u", token="t")
    evt = p.parse_webhook_event(
        payload={
            "webhookEvent": "jira:issue_created",
            "issue": {
                "id": "10",
                "key": "ENG-2",
                "fields": {
                    "summary": "s",
                    "description": "d",
                    "status": {"name": "Todo"},
                    "labels": [],
                },
            },
            "user": {"displayName": "Alice"},
        },
        headers={},
    )
    assert evt is not None
    assert evt.kind == "created"


def test_webhook_ignores_payload_without_issue() -> None:
    p = JiraCloudTracker(site=SITE, email="u", token="t")
    assert p.parse_webhook_event({"foo": 1}, headers={}) is None
