"""Tests for the Linear tracker."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.issues.providers.linear import LinearTracker


@pytest.mark.asyncio
async def test_read_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "issue": {
                            "id": "iid",
                            "identifier": "ENG-7",
                            "title": "T",
                            "description": "D",
                            "url": "https://linear.app/x/issue/ENG-7",
                            "labels": {"nodes": [{"name": "bug"}]},
                            "state": {"name": "In Progress"},
                        }
                    }
                },
            )
        )
        p = LinearTracker(api_key="lin_key")
        i = await p.read_issue(project="ENG", external_id="iid")
    assert i.external_id == "ENG-7"
    assert "bug" in i.labels
    assert i.status == "In Progress"


@pytest.mark.asyncio
async def test_comment_issue_posts_graphql_mutation() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200, json={"data": {"commentCreate": {"success": True}}}
            )
        )
        p = LinearTracker(api_key="k")
        await p.comment_issue(project="ENG", external_id="iid", body="hi")


def test_webhook_create_action_emits_created() -> None:
    p = LinearTracker(api_key="k")
    ev = p.parse_webhook_event(
        payload={
            "type": "Issue",
            "action": "create",
            "data": {
                "id": "iid",
                "identifier": "ENG-9",
                "title": "x",
                "description": "y",
                "url": "https://linear.app/x/issue/ENG-9",
                "labels": {"nodes": [{"name": "worker"}]},
                "state": {"name": "Todo"},
            },
            "actor": {"name": "Alice"},
        },
        headers={},
    )
    assert ev is not None
    assert ev.kind == "created"
    assert ev.actor == "Alice"


def test_webhook_rejects_when_signature_missing_and_secret_required() -> None:
    p = LinearTracker(api_key="k", webhook_secret="shh")
    assert p.parse_webhook_event({"type": "Issue"}, headers={}) is None
