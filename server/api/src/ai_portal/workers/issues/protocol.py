"""Issue-tracker protocol — pluggable issue-system backend.

Concrete providers (jira_cloud, linear, github_issues, gitlab_issues,
azure_boards) implement this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class Issue:
    """Provider-agnostic issue snapshot."""

    id: str
    external_id: str
    title: str
    body: str
    url: str
    labels: list[str]
    status: str
    repo_hint: str | None


@dataclass
class IssueWebhookEvent:
    """Parsed issue webhook payload."""

    kind: str
    issue: Issue
    actor: str
    raw: dict


@runtime_checkable
class IssueTracker(Protocol):
    """Contract every issue-tracker backend must satisfy."""

    name: str

    async def list_issues(
        self, *, project: str, query: str | None = None
    ) -> list[Issue]: ...

    async def read_issue(self, *, project: str, external_id: str) -> Issue: ...

    async def comment_issue(
        self, *, project: str, external_id: str, body: str
    ) -> None: ...

    async def set_status(
        self, *, project: str, external_id: str, status: str
    ) -> None: ...

    def parse_webhook_event(
        self, payload: dict, headers: dict
    ) -> IssueWebhookEvent | None: ...
