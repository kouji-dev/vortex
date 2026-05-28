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
from ai_portal.workers.approvals.decision import (
    AlreadyDecided,
    DecisionResult,
    NotAuthorized,
    record_decision,
)
from ai_portal.workers.types import TaskStatus, can_transition


class WorkersError(Exception):
    """Base error for the workers service."""


class NotFound(WorkersError):
    """Resource missing or not visible to this actor."""


class IllegalTransition(WorkersError):
    """Status transition rejected by the state machine."""


class ApprovalConflict(WorkersError):
    """Approval already terminal or approver not authorized."""


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


def update_pool(
    db: Session,
    *,
    org_id: _uuid.UUID,
    pool_id: _uuid.UUID,
    **fields: Any,
) -> WorkerPool:
    """Partial update — only keys provided in ``fields`` are written.

    ``settings`` is mapped onto ``settings_json``;
    ``repo_allow_list`` onto ``repo_allow_list_json`` (mirroring
    :func:`create_pool`).
    """
    row = get_pool(db, org_id=org_id, pool_id=pool_id)
    if "name" in fields and fields["name"] is not None:
        row.name = str(fields["name"])
    if "template" in fields and fields["template"] is not None:
        row.template = str(fields["template"])
    if "sandbox_provider" in fields and fields["sandbox_provider"] is not None:
        row.sandbox_provider = str(fields["sandbox_provider"])
    if "repo_allow_list" in fields and fields["repo_allow_list"] is not None:
        row.repo_allow_list_json = list(fields["repo_allow_list"])
    if "budget_cents_per_task" in fields and fields["budget_cents_per_task"] is not None:
        row.budget_cents_per_task = int(fields["budget_cents_per_task"])
    if "default_model" in fields and fields["default_model"] is not None:
        row.default_model = str(fields["default_model"])
    if "settings" in fields and fields["settings"] is not None:
        row.settings_json = dict(fields["settings"])
    if "enabled" in fields and fields["enabled"] is not None:
        row.enabled = bool(fields["enabled"])
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


def replay_task(
    db: Session,
    *,
    org_id: _uuid.UUID,
    task_id: _uuid.UUID,
    actor_id: str | None,
) -> WorkerTask:
    """Re-submit a historic task as a new task.

    Loads the original row (tenant-scoped), builds a fresh
    :class:`TaskInput` via :mod:`workers.replay`, then calls
    :func:`submit_task` so the new task takes the same path as any
    other submission. Stamps ``replay_of=<orig_id>`` into the trigger
    payload for audit/correlation.
    """
    from ai_portal.workers.replay.service import build_replay_input

    orig = get_task(db, org_id=org_id, task_id=task_id)
    ri = build_replay_input(task_row=orig, actor_id=actor_id)
    new = submit_task(
        db,
        org_id=org_id,
        pool_id=_uuid.UUID(ri.pool_id),
        title=ri.task_input.title,
        description=ri.task_input.description,
        repo=ri.task_input.repo,
        base_branch=ri.task_input.base_branch,
        trigger_source=ri.trigger_source,
        trigger_payload=dict(ri.task_input.extra),
        created_by=actor_id,
    )
    return new


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
    """Record one approver's vote against an M-of-N approval.

    Behaviour:

    - ``required_approvers`` is the M (NULL or 0 treated as 1 for
      backward compat with single-approver rows).
    - ``approver_ids_json`` is the optional N allow-list. Empty list =
      anyone can vote.
    - Each vote is appended to ``approvers_decided_json`` with a
      timestamp. ``votes_json`` keeps the latest vote per approver for
      fast lookup.
    - Flips to ``approved`` only when M distinct ``approve`` votes are
      collected. Any ``reject`` short-circuits to ``rejected``.
    - Re-voting on a resolved (approved/rejected) approval raises
      :class:`ApprovalConflict`.
    """
    row = db.execute(
        select(WorkerApproval).where(WorkerApproval.id == approval_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"approval {approval_id} not found")
    # tenant-check via the parent task
    get_task(db, org_id=org_id, task_id=row.task_id)

    if decided_by is None:
        raise ApprovalConflict("decided_by required to record an M-of-N vote")

    current = DecisionResult(
        state=row.state or "pending",
        votes=dict(row.votes_json or {}),
    )
    required = int(row.required_approvers or 1) or 1
    allowed = list(row.approver_ids_json or []) or None
    try:
        new = record_decision(
            current=current,
            approver_id=decided_by,
            decision=decision,
            required_approvers=required,
            allowed_approver_ids=allowed,
            reason=reason,
        )
    except (AlreadyDecided, NotAuthorized) as e:
        raise ApprovalConflict(str(e)) from e

    # Persist runtime state.
    row.state = new.state
    row.votes_json = dict(new.votes)
    # Append-only audit trail.
    trail = list(row.approvers_decided_json or [])
    trail.append(
        {
            "user_id": decided_by,
            "decision": decision,
            "ts": _utcnow().isoformat(),
            "reason": reason,
        }
    )
    row.approvers_decided_json = trail
    # Single-approver compat fields stay in sync for legacy readers.
    row.reason = reason
    if new.state != "pending":
        row.decision = "approve" if new.state == "approved" else "reject"
        row.decided_at = _utcnow()
        row.decided_by = decided_by
    db.flush()
    return row
