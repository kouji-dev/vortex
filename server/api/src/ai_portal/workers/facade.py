"""Module-public facade for cross-module callers.

Chat, assistants, and trigger sources call into the workers module through
this thin layer so they never depend on internal router/service shapes.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy.orm import Session

from ai_portal.workers import service as svc
from ai_portal.workers.events.writer import EventWriter, get_writer
from ai_portal.workers.types import TaskInput


def submit_task(
    db: Session,
    *,
    org_id: _uuid.UUID,
    task_input: TaskInput,
    trigger_source: str = "rest_api",
    pool_id: _uuid.UUID | None = None,
    created_by: str | None = None,
    trigger_payload: dict[str, Any] | None = None,
):
    """Submit a worker task. Returns the persisted ``WorkerTask``."""
    return svc.submit_task(
        db,
        org_id=org_id,
        pool_id=pool_id,
        title=task_input.title,
        description=task_input.description,
        repo=task_input.repo,
        base_branch=task_input.base_branch,
        trigger_source=trigger_source,
        trigger_payload=trigger_payload or dict(task_input.extra),
        created_by=created_by,
    )


def cancel_task(
    db: Session, *, org_id: _uuid.UUID, task_id: _uuid.UUID, reason: str | None = None
):
    """Cancel a running task. Idempotent."""
    return svc.cancel_task(db, org_id=org_id, task_id=task_id, reason=reason)


def get_event_writer() -> EventWriter:
    """Return the process-wide ``EventWriter`` singleton."""
    return get_writer()
