"""Linear webhook trigger — fires when a worker label is applied."""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class LinearWebhookTrigger:
    """Trigger that fires on Linear Issue events with the worker label."""

    kind = TriggerSourceKind.linear_webhook

    def __init__(
        self,
        *,
        team_to_repo: dict[str, str],
        worker_label: str = "worker",
    ) -> None:
        self._map = dict(team_to_repo)
        self._label = worker_label

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        if payload.get("type") != "Issue":
            return None
        data = payload.get("data") or {}
        labels_field = data.get("labels", {})
        if isinstance(labels_field, dict):
            labels = [
                n.get("name", "") for n in labels_field.get("nodes", []) or []
            ]
        elif isinstance(labels_field, list):
            labels = [
                lbl.get("name", "") if isinstance(lbl, dict) else str(lbl)
                for lbl in labels_field
            ]
        else:
            labels = []
        if self._label not in labels:
            return None
        identifier = data.get("identifier") or ""
        team = identifier.split("-", 1)[0] if "-" in identifier else ""
        repo = self._map.get(team)
        if not repo:
            return None
        return TaskInput(
            title=data.get("title", "") or identifier or "Linear task",
            description=data.get("description", "") or "",
            repo=repo,
            base_branch="main",
            extra={"issue_id": identifier, "source": "linear"},
        )
