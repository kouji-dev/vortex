"""Tests for the bundled trigger sources + registry."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ai_portal.workers.triggers import registry
from ai_portal.workers.triggers.protocol import TriggerSource
from ai_portal.workers.triggers.providers.chat import ChatTrigger
from ai_portal.workers.triggers.providers.github_issue_comment import (
    GitHubIssueCommentTrigger,
)
from ai_portal.workers.triggers.providers.github_pr_comment import (
    GitHubPrCommentTrigger,
)
from ai_portal.workers.triggers.providers.jira_webhook import JiraWebhookTrigger
from ai_portal.workers.triggers.providers.linear_webhook import (
    LinearWebhookTrigger,
)
from ai_portal.workers.triggers.providers.rest_api import RestApiTrigger
from ai_portal.workers.triggers.providers.schedule_cron import (
    ScheduleCronTrigger,
    cron_matches,
    next_fire_at,
)
from ai_portal.workers.types import TriggerSourceKind


def test_chat_trigger_parses_assignment() -> None:
    t = ChatTrigger()
    ti = t.parse(
        {
            "kind": "assign_to_worker",
            "title": "Fix",
            "description": "details",
            "repo": "acme/api",
            "conversation_id": "c1",
        }
    )
    assert ti is not None
    assert ti.title == "Fix"
    assert ti.repo == "acme/api"
    assert ti.extra["conversation_id"] == "c1"


def test_chat_trigger_ignores_other_kinds() -> None:
    assert ChatTrigger().parse({"kind": "message", "text": "hi"}) is None


def test_chat_trigger_requires_title_and_repo() -> None:
    assert ChatTrigger().parse({"kind": "assign_to_worker"}) is None


def test_rest_api_validates_required_fields() -> None:
    t = RestApiTrigger()
    assert t.parse({"description": "x"}) is None
    ti = t.parse({"title": "T", "description": "D", "repo": "x/y"})
    assert ti is not None
    assert ti.base_branch == "main"


def test_rest_api_passes_through_extra_and_base() -> None:
    ti = RestApiTrigger().parse(
        {
            "title": "T",
            "repo": "x/y",
            "base_branch": "develop",
            "extra": {"priority": "high"},
        }
    )
    assert ti is not None
    assert ti.base_branch == "develop"
    assert ti.extra["priority"] == "high"


def test_jira_webhook_fires_when_label_present() -> None:
    t = JiraWebhookTrigger(project_to_repo={"ENG": "acme/api"})
    ti = t.parse(
        {
            "issue": {
                "key": "ENG-42",
                "fields": {
                    "summary": "Fix bug",
                    "description": "details",
                    "labels": ["worker"],
                },
            }
        }
    )
    assert ti is not None
    assert ti.title == "Fix bug"
    assert ti.repo == "acme/api"
    assert ti.extra["issue_key"] == "ENG-42"


def test_jira_webhook_ignores_unlabeled() -> None:
    t = JiraWebhookTrigger(project_to_repo={"ENG": "acme/api"})
    assert (
        t.parse({"issue": {"key": "ENG-1", "fields": {"labels": []}}})
        is None
    )


def test_jira_webhook_ignores_unmapped_project() -> None:
    t = JiraWebhookTrigger(project_to_repo={"ENG": "acme/api"})
    assert (
        t.parse(
            {
                "issue": {
                    "key": "OPS-1",
                    "fields": {"summary": "x", "labels": ["worker"]},
                }
            }
        )
        is None
    )


def test_linear_webhook_fires_on_worker_label() -> None:
    t = LinearWebhookTrigger(team_to_repo={"ENG": "acme/api"})
    ti = t.parse(
        {
            "type": "Issue",
            "data": {
                "identifier": "ENG-9",
                "title": "T",
                "description": "D",
                "labels": {"nodes": [{"name": "worker"}]},
            },
        }
    )
    assert ti is not None
    assert ti.repo == "acme/api"
    assert ti.extra["issue_id"] == "ENG-9"


def test_linear_webhook_ignores_non_issue_payload() -> None:
    t = LinearWebhookTrigger(team_to_repo={"ENG": "acme/api"})
    assert t.parse({"type": "Comment"}) is None


def test_github_issue_comment_fires_on_phrase() -> None:
    t = GitHubIssueCommentTrigger()
    ti = t.parse(
        {
            "comment": {"body": "/worker fix the auth bug", "id": 99},
            "issue": {"number": 7, "title": "T", "body": "B"},
            "repository": {
                "full_name": "acme/api",
                "default_branch": "main",
            },
        }
    )
    assert ti is not None
    assert "fix the auth bug" in ti.title
    assert ti.repo == "acme/api"
    assert ti.extra["issue_number"] == 7


def test_github_issue_comment_ignores_pull_request_payloads() -> None:
    t = GitHubIssueCommentTrigger()
    assert (
        t.parse(
            {
                "comment": {"body": "/worker x"},
                "issue": {"pull_request": {}, "number": 1},
                "repository": {"full_name": "acme/api"},
            }
        )
        is None
    )


def test_github_pr_comment_fires_on_phrase() -> None:
    t = GitHubPrCommentTrigger()
    ti = t.parse(
        {
            "comment": {"body": "/worker reword this", "id": 1},
            "issue": {"pull_request": {"url": "x"}, "number": 42},
            "repository": {"full_name": "acme/api"},
        }
    )
    assert ti is not None
    assert ti.extra["pr_number"] == 42


def test_github_pr_comment_ignores_other_phrases() -> None:
    t = GitHubPrCommentTrigger(phrase="/agent")
    assert (
        t.parse(
            {
                "comment": {"body": "/worker x"},
                "issue": {"pull_request": {"url": "x"}, "number": 1},
                "repository": {"full_name": "acme/api"},
            }
        )
        is None
    )


def test_schedule_cron_parses_template() -> None:
    t = ScheduleCronTrigger()
    ti = t.parse(
        {
            "schedule_id": "s-1",
            "template": {
                "title": "Nightly cleanup",
                "description": "...",
                "repo": "acme/api",
            },
        }
    )
    assert ti is not None
    assert ti.title == "Nightly cleanup"
    assert ti.extra["schedule_id"] == "s-1"
    assert ti.extra["source"] == "schedule_cron"


def test_cron_matches_basic() -> None:
    assert cron_matches("*/5 * * * *", datetime(2026, 5, 28, 10, 5))
    assert not cron_matches("*/5 * * * *", datetime(2026, 5, 28, 10, 7))
    assert cron_matches("0 0 * * *", datetime(2026, 5, 28, 0, 0))
    assert cron_matches("30 9 * * *", datetime(2026, 5, 28, 9, 30))


def test_next_fire_at_advances_to_minute_boundary() -> None:
    now = datetime(2026, 5, 28, 9, 28)
    n = next_fire_at("*/5 * * * *", after=now)
    assert n == datetime(2026, 5, 28, 9, 30)


def test_next_fire_at_handles_hourly() -> None:
    now = datetime(2026, 5, 28, 9, 30)
    n = next_fire_at("0 * * * *", after=now)
    assert n == datetime(2026, 5, 28, 10, 0)


def test_registry_register_and_lookup() -> None:
    registry.clear()
    chat = ChatTrigger()
    registry.register(chat)
    assert registry.get(TriggerSourceKind.chat) is chat
    assert TriggerSourceKind.chat in registry.all_triggers()
    registry.clear()
    with pytest.raises(KeyError):
        registry.get(TriggerSourceKind.chat)


def test_all_triggers_satisfy_protocol() -> None:
    triggers = [
        ChatTrigger(),
        RestApiTrigger(),
        JiraWebhookTrigger(project_to_repo={"X": "a/b"}),
        LinearWebhookTrigger(team_to_repo={"X": "a/b"}),
        GitHubIssueCommentTrigger(),
        GitHubPrCommentTrigger(),
        ScheduleCronTrigger(),
    ]
    for t in triggers:
        assert isinstance(t, TriggerSource)
