"""Gateway playground — saved snapshots + multi-model run.

Public surface:

- :class:`PlaygroundSession` — SQLAlchemy ORM model.
- :class:`PlaygroundService` — CRUD + ``run_snapshot`` orchestrator.
- :data:`router` — FastAPI router mounted under ``/v1/gateway/playground``.
"""

from __future__ import annotations

from ai_portal.gateway.playground.model import PlaygroundSession
from ai_portal.gateway.playground.router import router
from ai_portal.gateway.playground.service import PlaygroundService, SessionView

__all__ = [
    "PlaygroundService",
    "PlaygroundSession",
    "SessionView",
    "router",
]
