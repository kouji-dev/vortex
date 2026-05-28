"""Tests for issue-tracker webhook → match resolver."""

from __future__ import annotations

from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent
from ai_portal.workers.triggers.webhooks import resolve_match


def _issue(
    *,
    external_id: str,
    title: str = "Bug",
    body: str = "...",
    labels: list[str] | None = None,
    repo_hint: str | None = None,
) -> Issue:
    return Issue(
        id="1",
        external_id=external_id,
        title=title,
        body=body,
        url="https://example.com/i/1",
        labels=labels or [],
        status="open",
        repo_hint=repo_hint,
    )


def _ev(kind: str, issue: Issue, actor: str = "alice") -> IssueWebhookEvent:
    return IssueWebhookEvent(kind=kind, issue=issue, actor=actor, raw={})


def test_jira_payload_matches_by_project_key_prefix() -> None:
    ev = _ev(
        "labeled",
        _issue(
            external_id="PROJ-42",
            title="Fix login",
            labels=["bug", "ai-worker"],
        ),
    )
    mapping = {
        "PROJ": {
            "pool_id": "pool-aaa",
            "trigger_label": "ai-worker",
            "repo": "acme/api",
        }
    }
    m = resolve_match(ev, project_mapping=mapping)
    assert m is not None
    assert m.pool_id == "pool-aaa"
    assert m.title == "Fix login"
    assert m.repo == "acme/api"
    assert m.trigger_payload["issue_external_id"] == "PROJ-42"


def test_linear_matches_by_repo_hint() -> None:
    ev = _ev(
        "labeled",
        _issue(
            external_id="LIN-7",
            labels=["needs-ai"],
            repo_hint="acme/web",
        ),
    )
    mapping = {
        "acme/web": {
            "pool_id": "pool-web",
            "trigger_label": "needs-ai",
        }
    }
    m = resolve_match(ev, project_mapping=mapping)
    assert m is not None
    assert m.pool_id == "pool-web"
    assert m.repo == "acme/web"


def test_github_issues_matches_owner_repo() -> None:
    ev = _ev(
        "labeled",
        _issue(
            external_id="123",
            labels=["bot:fix"],
            repo_hint="acme/api",
        ),
    )
    mapping = {
        "acme/api": {
            "pool_id": "pool-x",
            "trigger_label": "bot:fix",
        }
    }
    m = resolve_match(ev, project_mapping=mapping)
    assert m is not None
    assert m.pool_id == "pool-x"


def test_no_match_when_label_missing() -> None:
    ev = _ev(
        "labeled",
        _issue(external_id="PROJ-1", labels=["bug"]),
    )
    mapping = {"PROJ": {"pool_id": "p", "trigger_label": "ai-worker"}}
    assert resolve_match(ev, project_mapping=mapping) is None


def test_no_match_when_project_not_mapped() -> None:
    ev = _ev(
        "labeled",
        _issue(external_id="OTHER-1", labels=["ai-worker"]),
    )
    mapping = {"PROJ": {"pool_id": "p", "trigger_label": "ai-worker"}}
    assert resolve_match(ev, project_mapping=mapping) is None


def test_no_match_when_event_kind_not_allowed() -> None:
    ev = _ev(
        "commented",
        _issue(external_id="PROJ-1", labels=["ai-worker"]),
    )
    mapping = {
        "PROJ": {
            "pool_id": "p",
            "trigger_label": "ai-worker",
            "auto_submit_on": ["labeled"],
        }
    }
    assert resolve_match(ev, project_mapping=mapping) is None


def test_match_when_auto_submit_on_created() -> None:
    ev = _ev(
        "created",
        _issue(external_id="PROJ-1", labels=["ai-worker"]),
    )
    mapping = {
        "PROJ": {
            "pool_id": "p",
            "trigger_label": "ai-worker",
            "auto_submit_on": ["created", "labeled"],
            "repo": "acme/api",
        }
    }
    m = resolve_match(ev, project_mapping=mapping)
    assert m is not None
    assert m.trigger_payload["event_kind"] == "created"


def test_match_without_trigger_label_when_blank() -> None:
    ev = _ev(
        "created",
        _issue(external_id="PROJ-1", labels=[]),
    )
    mapping = {
        "PROJ": {
            "pool_id": "p",
            "trigger_label": "",
            "auto_submit_on": ["created"],
            "repo": "acme/api",
        }
    }
    m = resolve_match(ev, project_mapping=mapping)
    assert m is not None


def test_no_match_when_pool_id_missing() -> None:
    ev = _ev(
        "labeled",
        _issue(external_id="PROJ-1", labels=["ai-worker"]),
    )
    mapping = {"PROJ": {"trigger_label": "ai-worker"}}
    assert resolve_match(ev, project_mapping=mapping) is None


def test_base_branch_override() -> None:
    ev = _ev(
        "labeled",
        _issue(external_id="PROJ-1", labels=["ai-worker"], repo_hint="acme/api"),
    )
    mapping = {
        "acme/api": {
            "pool_id": "p",
            "trigger_label": "ai-worker",
            "base_branch": "develop",
        }
    }
    m = resolve_match(ev, project_mapping=mapping)
    assert m is not None
    assert m.base_branch == "develop"
