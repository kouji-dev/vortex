"""Chat trigger — turns an ``assign_to_worker`` event into a ``TaskInput``."""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class ChatTrigger:
    """Parses chat-emitted assignments to a TaskInput."""

    kind = TriggerSourceKind.chat

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        if payload.get("kind") != "assign_to_worker":
            return None
        title = payload.get("title") or payload.get("summary")
        repo = payload.get("repo")
        if not title or not repo:
            return None
        return TaskInput(
            title=title,
            description=payload.get("description", "") or "",
            repo=repo,
            base_branch=payload.get("base_branch", "main"),
            extra={
                "conversation_id": payload.get("conversation_id"),
                "actor_id": payload.get("actor_id"),
            },
        )
