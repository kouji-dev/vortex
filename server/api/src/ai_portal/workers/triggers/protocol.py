"""Trigger source protocol — pluggable task-submission origin.

Concrete sources (chat, rest_api, jira_webhook, linear_webhook,
github_issue_comment, github_pr_comment, schedule_cron) implement this
contract. Each parser takes a raw payload and returns a ``TaskInput`` or
``None`` if the payload is irrelevant.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_portal.workers.types import TaskInput, TriggerSourceKind


@runtime_checkable
class TriggerSource(Protocol):
    """Contract every trigger source must satisfy."""

    kind: TriggerSourceKind

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None: ...
