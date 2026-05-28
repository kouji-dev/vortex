"""REST API trigger — validates submission body against the TaskInput shape."""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class RestApiTrigger:
    """Direct POST /v1/workers/tasks submissions."""

    kind = TriggerSourceKind.rest_api

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        title = payload.get("title")
        description = payload.get("description", "")
        repo = payload.get("repo")
        if not title or not repo:
            return None
        return TaskInput(
            title=title,
            description=description or "",
            repo=repo,
            base_branch=payload.get("base_branch", "main"),
            extra=dict(payload.get("extra", {}) or {}),
        )
