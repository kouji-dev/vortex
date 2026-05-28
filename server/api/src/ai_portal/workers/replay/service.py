"""Task replay — build a fresh :class:`TaskInput` from a historic task row.

The replay flow:
1. Load the original ``WorkerTask`` row (caller-supplied).
2. Capture the canonical inputs that drove the original run: title,
   description, repo, base_branch, trigger payload.
3. Stamp a ``replay_of`` marker into ``extra`` so audit can correlate.

The actual submission goes through the same path as a new task — replay
is just the input builder + a small wrapper that calls the orchestrator's
public submit. The orchestrator is wired separately, so this file stays
pure (no DB / no orchestrator imports).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_portal.workers.types import TaskInput


@dataclass(frozen=True)
class ReplayInput:
    """Materialized replay input — ready to hand to the orchestrator."""

    task_input: TaskInput
    org_id: str
    pool_id: str
    trigger_source: str
    parent_task_id: str


@dataclass(frozen=True)
class ReplayResult:
    """Outcome reported after submitting a replay (caller fills it in)."""

    new_task_id: str
    parent_task_id: str


def build_replay_input(
    *,
    task_row: Any,
    actor_id: str | None = None,
) -> ReplayInput:
    """Construct a :class:`ReplayInput` from a ``WorkerTask`` row-like object.

    The row must expose: ``id``, ``org_id``, ``pool_id``, ``title``,
    ``description``, ``repo``, ``base_branch``, ``trigger_source``,
    ``trigger_payload_json``. We deliberately ignore the row's status —
    completed / failed / cancelled tasks are all replayable.
    """
    parent_id = str(task_row.id)
    extra: dict[str, Any] = dict(getattr(task_row, "trigger_payload_json", {}) or {})
    extra["replay_of"] = parent_id
    if actor_id:
        extra["replay_actor_id"] = actor_id

    ti = TaskInput(
        title=task_row.title,
        description=task_row.description,
        repo=task_row.repo or "",
        base_branch=task_row.base_branch or "main",
        extra=extra,
    )
    return ReplayInput(
        task_input=ti,
        org_id=str(task_row.org_id),
        pool_id=str(task_row.pool_id),
        trigger_source=task_row.trigger_source,
        parent_task_id=parent_id,
    )
