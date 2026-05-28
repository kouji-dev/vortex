"""Jira webhook trigger — fires when issue is labeled with the worker label.

The project → repo mapping is provided at construction time (mirrors the
``IssueTrackerIntegration.project_mapping_json`` column).
"""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class JiraWebhookTrigger:
    """Trigger that fires on Jira ``issue_updated`` with the worker label."""

    kind = TriggerSourceKind.jira_webhook

    def __init__(
        self,
        *,
        project_to_repo: dict[str, str],
        worker_label: str = "worker",
    ) -> None:
        self._map = dict(project_to_repo)
        self._label = worker_label

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        issue = payload.get("issue") or {}
        fields = issue.get("fields", {}) or {}
        labels = fields.get("labels", []) or []
        if self._label not in labels:
            return None
        key = issue.get("key", "")
        project = key.split("-", 1)[0] if "-" in key else ""
        repo = self._map.get(project)
        if not repo:
            return None
        return TaskInput(
            title=fields.get("summary", "") or key or "Jira task",
            description=str(fields.get("description") or ""),
            repo=repo,
            base_branch="main",
            extra={"issue_key": key, "source": "jira"},
        )
