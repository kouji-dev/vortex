"""Tests for the GitHub Issues tracker."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.issues.providers.github_issues import (
    GitHubIssuesTracker,
)


@pytest.mark.asyncio
async def test_read_issue() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.github.com/repos/acme/api/issues/42").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "number": 42,
                    "html_url": "https://github.com/acme/api/issues/42",
                    "state": "open",
                    "title": "Bug",
                    "body": "details",
                    "labels": [{"name": "worker"}],
                },
            )
        )
        p = GitHubIssuesTracker(token="t")
        i = await p.read_issue(project="acme/api", external_id="42")
    assert i.title == "Bug"
    assert "worker" in i.labels
    assert i.repo_hint == "acme/api"


@pytest.mark.asyncio
async def test_list_issues_filters_out_pull_requests() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.github.com/repos/acme/api/issues").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": 1, "number": 1, "title": "A", "state": "open", "labels": [], "html_url": "u"},
                    {"id": 2, "number": 2, "title": "B", "state": "open", "labels": [],
                     "html_url": "u", "pull_request": {}},
                ],
            )
        )
        p = GitHubIssuesTracker(token="t")
        issues = await p.list_issues(project="acme/api")
    assert len(issues) == 1
    assert issues[0].title == "A"


@pytest.mark.asyncio
async def test_set_status_closes_for_done() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        route = mock.patch("https://api.github.com/repos/acme/api/issues/42").mock(
            return_value=httpx.Response(200, json={})
        )
        p = GitHubIssuesTracker(token="t")
        await p.set_status(project="acme/api", external_id="42", status="Done")
    assert route.called
    sent = route.calls[0].request
    assert b'"state": "closed"' in sent.content or b'"state":"closed"' in sent.content


def test_webhook_labeled_emits_labeled() -> None:
    p = GitHubIssuesTracker(token="t")
    ev = p.parse_webhook_event(
        payload={
            "action": "labeled",
            "issue": {
                "id": 1, "number": 9, "html_url": "x", "state": "open",
                "title": "t", "body": "", "labels": [{"name": "worker"}],
            },
            "repository": {"full_name": "acme/api"},
            "sender": {"login": "alice"},
        },
        headers={},
    )
    assert ev is not None
    assert ev.kind == "labeled"


def test_webhook_skips_pull_request_payloads() -> None:
    p = GitHubIssuesTracker(token="t")
    assert (
        p.parse_webhook_event(
            payload={"action": "opened", "issue": {"pull_request": {}}},
            headers={},
        )
        is None
    )
