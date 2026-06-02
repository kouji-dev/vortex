"""Worker-instance service — worker-centric layer ("a worker IS a task").

Thin sync business logic over the new ORM (:class:`Worker`,
:class:`WorkerInstanceRun`, :class:`WorkerRunChange`, :class:`WorkerMessage`).
Separate from the legacy task-centric :mod:`ai_portal.workers.service`.

The actual agent execution is **stubbed**: ``spawn_worker`` provisions a row
and conceptually launches the runtime, but real VM provisioning + agent-SDK
exec are not wired (see :mod:`ai_portal.workers.agent_runtime`). A run is
created on ``message`` but does not progress on its own — that is the
orchestrator/runner job, deferred.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.workers.agent_runtime import AgentRuntimeConfig
from ai_portal.workers.runtime_infer import infer_runtime
from ai_portal.workers.model import (
    Worker,
    WorkerInstanceRun,
    WorkerMessage,
    WorkerRunChange,
)
from ai_portal.workers.skills.registry import UnknownSkill, resolve_skills

# valid enum-like values (kept as plain strings to match column types)
WORKER_MODES = ("interactive", "autonomous")
WORKER_RUNTIMES = ("claude", "codex")
WORKER_STATES = ("idle", "provisioning", "running", "error", "stopped")
RUN_STATUSES = ("running", "error", "finished", "success")
MESSAGE_ROLES = ("user", "agent", "system")


class WorkersInstanceError(Exception):
    """Base error for the worker-instance service."""


class NotFound(WorkersInstanceError):
    """Resource missing or not visible to this actor."""


class InvalidArg(WorkersInstanceError):
    """Bad input (mode/runtime/skill/etc.)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── workers ──────────────────────────────────────────────────────


def spawn_worker(
    db: Session,
    *,
    org_id: _uuid.UUID,
    name: str,
    model: str,
    mode: str = "interactive",
    runtime: str | None = None,
    connector: dict[str, Any] | None = None,
    repo_url: str | None = None,
    pool_id: _uuid.UUID | None = None,
    trigger_source: str | None = None,
    trigger_payload: dict[str, Any] | None = None,
    skills: list[str] | None = None,
    created_by: str | None = None,
) -> Worker:
    """Create a worker = define the task. Validates inputs; provisions a row.

    Real VM provision + agent launch is stubbed (state starts ``provisioning``).
    The orchestrator transitions ``provisioning → idle`` once the sandbox is up.
    """
    if mode not in WORKER_MODES:
        raise InvalidArg(f"invalid mode {mode!r}")
    try:
        runtime = runtime or infer_runtime(model)
    except ValueError as exc:
        raise InvalidArg(str(exc)) from exc
    if runtime not in WORKER_RUNTIMES:
        raise InvalidArg(f"invalid runtime {runtime!r}")
    if skills:
        try:
            resolve_skills(skills)
        except UnknownSkill as e:  # noqa: BLE001
            raise InvalidArg(f"unknown skill {e}") from e

    connector = dict(connector or {})
    if skills:
        connector["skills"] = list(skills)

    row = Worker(
        org_id=org_id,
        pool_id=pool_id,
        name=name,
        state="provisioning",
        mode=mode,
        model=model,
        runtime=runtime,
        connector_json=connector,
        repo_url=repo_url,
        trigger_source=trigger_source,
        trigger_payload_json=dict(trigger_payload or {}),
        created_by=created_by,
        last_active_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    # TODO(agent-sdk-boundary): kick off real sandbox provision + runtime.start
    # here (async, out of band). Until then the worker sits in ``provisioning``.
    return row


def list_workers(
    db: Session, *, org_id: _uuid.UUID, state: str | None = None, limit: int = 100
) -> list[Worker]:
    stmt = select(Worker).where(Worker.org_id == org_id)
    if state:
        stmt = stmt.where(Worker.state == state)
    stmt = stmt.order_by(Worker.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_worker(db: Session, *, org_id: _uuid.UUID, worker_id: _uuid.UUID) -> Worker:
    row = db.execute(
        select(Worker).where(Worker.org_id == org_id, Worker.id == worker_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"worker {worker_id} not found")
    return row


def stop_worker(db: Session, *, org_id: _uuid.UUID, worker_id: _uuid.UUID) -> Worker:
    """Stop a worker: release its sandbox, mark ``stopped``. Idempotent."""
    row = get_worker(db, org_id=org_id, worker_id=worker_id)
    if row.state != "stopped":
        row.state = "stopped"
        row.last_active_at = _utcnow()
        # TODO(agent-sdk-boundary): kill the runtime + release the sandbox/VM.
        db.flush()
    return row


# ── runs (one per user message) ──────────────────────────────────


def _next_seq_no(db: Session, *, worker_id: _uuid.UUID) -> int:
    current = db.execute(
        select(func.max(WorkerInstanceRun.seq_no)).where(
            WorkerInstanceRun.worker_id == worker_id
        )
    ).scalar_one_or_none()
    return int(current or 0) + 1


def start_run(
    db: Session,
    *,
    org_id: _uuid.UUID,
    worker_id: _uuid.UUID,
    user_message: str,
) -> tuple[WorkerInstanceRun, WorkerMessage]:
    """Start a run from a user message. Persists the user chat message + run.

    Creates the run in ``running`` and records the worker chat message. The
    agent work itself is stubbed — the run does not advance on its own.
    """
    worker = get_worker(db, org_id=org_id, worker_id=worker_id)
    if worker.state == "stopped":
        raise InvalidArg("worker is stopped")

    seq = _next_seq_no(db, worker_id=worker_id)
    run = WorkerInstanceRun(
        worker_id=worker_id,
        seq_no=seq,
        user_message=user_message,
        status="running",
        sandbox_id=worker.sandbox_id,
    )
    db.add(run)
    db.flush()

    msg = WorkerMessage(
        worker_id=worker_id, run_id=run.id, role="user", content=user_message
    )
    db.add(msg)

    worker.state = "running"
    worker.last_active_at = _utcnow()
    db.flush()
    # TODO(agent-sdk-boundary): hand `user_message` to the runtime
    # (runtime.send_message) and stream AgentEvents → worker_messages /
    # worker_run_changes / SSE. Stubbed: no agent progress here.
    return run, msg


def list_runs(db: Session, *, worker_id: _uuid.UUID) -> list[WorkerInstanceRun]:
    return list(
        db.execute(
            select(WorkerInstanceRun)
            .where(WorkerInstanceRun.worker_id == worker_id)
            .order_by(WorkerInstanceRun.seq_no)
        )
        .scalars()
        .all()
    )


def get_run(db: Session, *, run_id: _uuid.UUID) -> WorkerInstanceRun:
    row = db.execute(
        select(WorkerInstanceRun).where(WorkerInstanceRun.id == run_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFound(f"run {run_id} not found")
    return row


def list_run_changes(db: Session, *, run_id: _uuid.UUID) -> list[WorkerRunChange]:
    return list(
        db.execute(
            select(WorkerRunChange)
            .where(WorkerRunChange.run_id == run_id)
            .order_by(WorkerRunChange.file_path)
        )
        .scalars()
        .all()
    )


# ── chat thread ──────────────────────────────────────────────────


def list_messages(db: Session, *, worker_id: _uuid.UUID) -> list[WorkerMessage]:
    return list(
        db.execute(
            select(WorkerMessage)
            .where(WorkerMessage.worker_id == worker_id)
            .order_by(WorkerMessage.ts)
        )
        .scalars()
        .all()
    )


# ── runtime config (gateway base_url wiring) ─────────────────────


def build_runtime_config(
    worker: Worker, *, gateway_base_url: str
) -> AgentRuntimeConfig:
    """Build the :class:`AgentRuntimeConfig` for a worker.

    Wires the worker's LLM path through the gateway (no-fake-providers
    directive): the in-sandbox agent's provider calls are pointed at
    ``gateway_base_url`` via the runtime's base_url env. Pure + testable.
    """
    skills = list((worker.connector_json or {}).get("skills", []))
    return AgentRuntimeConfig(
        model=worker.model,
        gateway_base_url=gateway_base_url,
        skills=skills,
        permission_mode="default",
    )
