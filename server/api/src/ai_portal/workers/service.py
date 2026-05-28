"""Workers service — thin business-logic layer over the ORM.

All DB calls are sync (matches project convention). Functions take a
``Session`` + the actor's ``org_id`` and never read globals.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.workers.model import (
    WorkerApproval,
    WorkerArtifact,
    WorkerEvent,
    WorkerPool,
    WorkerRun,
    WorkerTask,
)
from ai_portal.workers.types import TaskStatus, can_transition


class WorkersError(Exception):
    """Base error for the workers service."""


class NotFound(WorkersError):
    """Resource missing or not visible to this actor."""


class IllegalTransition(WorkersError):
    """Status transition rejected by the state machine."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── pools ────────────────────────────────────────────────────────


def list_pools(db: Session, *, org_id: _uuid.UUID) -> list[WorkerPool]:
    rows = (
        db.execute(
            select(WorkerPool).where(WorkerPool.org_id == org_id).order_by(WorkerPool.created_at)
        )
        .scalars()
        .all()
    )
    return list(rows)


def get_pool(db: Session, *, org_id: _uuid.UUID, pool_id: _uuid.UUID) -> WorkerPool:
    row = db.execute(
        select(WorkerPool).where(WorkerPool.org_id == org_id, WorkerPool.id == pool_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"pool {pool_id} not found")
    return row


def create_pool(
    db: Session,
    *,
    org_id: _uuid.UUID,
    name: str,
    template: str,
    sandbox_provider: str,
    repo_allow_list: list[str],
    budget_cents_per_task: int,
    default_model: str,
    settings: dict[str, Any],
    enabled: bool = True,
) -> WorkerPool:
    row = WorkerPool(
        org_id=org_id,
        name=name,
        template=template,
        sandbox_provider=sandbox_provider,
        repo_allow_list_json=list(repo_allow_list),
        budget_cents_per_task=int(budget_cents_per_task),
        default_model=default_model,
        settings_json=dict(settings),
        enabled=enabled,
    )
    db.add(row)
    db.flush()
    return row


def delete_pool(db: Session, *, org_id: _uuid.UUID, pool_id: _uuid.UUID) -> None:
    row = get_pool(db, org_id=org_id, pool_id=pool_id)
    db.delete(row)
    db.flush()


# ── tasks ────────────────────────────────────────────────────────


def list_tasks(
    db: Session,
    *,
    org_id: _uuid.UUID,
    pool_id: _uuid.UUID | None = None,
    status_filter: str | None = None,
    limit: int = 100,
) -> list[WorkerTask]:
    q = select(WorkerTask).where(WorkerTask.org_id == org_id)
    if pool_id is not None:
        q = q.where(WorkerTask.pool_id == pool_id)
    if status_filter:
        q = q.where(WorkerTask.status == status_filter)
    q = q.order_by(WorkerTask.created_at.desc()).limit(limit)
    return list(db.execute(q).scalars().all())


def get_task(db: Session, *, org_id: _uuid.UUID, task_id: _uuid.UUID) -> WorkerTask:
    row = db.execute(
        select(WorkerTask).where(WorkerTask.org_id == org_id, WorkerTask.id == task_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"task {task_id} not found")
    return row


def submit_task(
    db: Session,
    *,
    org_id: _uuid.UUID,
    pool_id: _uuid.UUID | None,
    title: str,
    description: str,
    repo: str,
    base_branch: str,
    trigger_source: str,
    trigger_payload: dict[str, Any],
    created_by: str | None,
) -> WorkerTask:
    # Resolve pool: if not provided, pick the first enabled pool for the org.
    if pool_id is None:
        pool = db.execute(
            select(WorkerPool)
            .where(WorkerPool.org_id == org_id, WorkerPool.enabled.is_(True))
            .order_by(WorkerPool.created_at)
            .limit(1)
        ).scalar_one_or_none()
        if pool is None:
            raise WorkersError("no enabled pool — create one before submitting tasks")
        pool_id = pool.id
    else:
        get_pool(db, org_id=org_id, pool_id=pool_id)  # raises if invisible
    row = WorkerTask(
        org_id=org_id,
        pool_id=pool_id,
        trigger_source=trigger_source,
        trigger_payload_json=dict(trigger_payload),
        title=title,
        description=description,
        repo=repo,
        base_branch=base_branch,
        status="queued",
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def transition_task(
    db: Session,
    *,
    task: WorkerTask,
    to: TaskStatus,
) -> WorkerTask:
    try:
        cur = TaskStatus(task.status)
    except ValueError as e:
        raise IllegalTransition(f"unknown current status {task.status}") from e
    if not can_transition(cur, to):
        raise IllegalTransition(f"{cur.value} -> {to.value} not allowed")
    task.status = to.value
    if to in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
        task.completed_at = _utcnow()
    db.flush()
    return task


def cancel_task(
    db: Session, *, org_id: _uuid.UUID, task_id: _uuid.UUID, reason: str | None = None
) -> WorkerTask:
    t = get_task(db, org_id=org_id, task_id=task_id)
    if t.status in ("completed", "cancelled", "failed"):
        return t  # idempotent
    return transition_task(db, task=t, to=TaskStatus.cancelled)


def pause_task(db: Session, *, org_id: _uuid.UUID, task_id: _uuid.UUID) -> WorkerTask:
    t = get_task(db, org_id=org_id, task_id=task_id)
    return transition_task(db, task=t, to=TaskStatus.paused)


def resume_task(db: Session, *, org_id: _uuid.UUID, task_id: _uuid.UUID) -> WorkerTask:
    t = get_task(db, org_id=org_id, task_id=task_id)
    return transition_task(db, task=t, to=TaskStatus.executing)


# ── runs / events / artifacts / approvals ───────────────────────


def list_runs(db: Session, *, task_id: _uuid.UUID) -> list[WorkerRun]:
    rows = db.execute(
        select(WorkerRun).where(WorkerRun.task_id == task_id).order_by(WorkerRun.attempt_no)
    ).scalars().all()
    return list(rows)


def list_events_for_task(
    db: Session,
    *,
    task_id: _uuid.UUID,
    after_ts: datetime | None = None,
    limit: int = 500,
) -> list[WorkerEvent]:
    run_ids = [r.id for r in list_runs(db, task_id=task_id)]
    if not run_ids:
        return []
    q = select(WorkerEvent).where(WorkerEvent.run_id.in_(run_ids))
    if after_ts is not None:
        q = q.where(WorkerEvent.ts > after_ts)
    q = q.order_by(WorkerEvent.ts).limit(limit)
    return list(db.execute(q).scalars().all())


def list_artifacts(db: Session, *, task_id: _uuid.UUID) -> list[WorkerArtifact]:
    run_ids = [r.id for r in list_runs(db, task_id=task_id)]
    if not run_ids:
        return []
    rows = db.execute(
        select(WorkerArtifact)
        .where(WorkerArtifact.run_id.in_(run_ids))
        .order_by(WorkerArtifact.created_at.desc())
    ).scalars().all()
    return list(rows)


def list_approvals(db: Session, *, task_id: _uuid.UUID) -> list[WorkerApproval]:
    rows = db.execute(
        select(WorkerApproval)
        .where(WorkerApproval.task_id == task_id)
        .order_by(WorkerApproval.requested_at.desc())
    ).scalars().all()
    return list(rows)


def decide_approval(
    db: Session,
    *,
    org_id: _uuid.UUID,
    approval_id: _uuid.UUID,
    decision: str,
    decided_by: str | None,
    reason: str | None = None,
) -> WorkerApproval:
    row = db.execute(
        select(WorkerApproval).where(WorkerApproval.id == approval_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"approval {approval_id} not found")
    # tenant-check via the parent task
    get_task(db, org_id=org_id, task_id=row.task_id)
    row.decision = decision
    row.decided_at = _utcnow()
    row.decided_by = decided_by
    row.reason = reason
    db.flush()
    return row
