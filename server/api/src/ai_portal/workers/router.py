"""Workers HTTP API — tasks / pools / events SSE / approvals / artifacts.

Routes (prefix ``/v1/workers``):

- ``POST   /tasks``                          — submit task
- ``GET    /tasks``                          — list tasks
- ``GET    /tasks/{id}``                     — get task
- ``GET    /tasks/{id}/runs``                — list runs
- ``GET    /tasks/{id}/events``              — SSE live stream (backfill + live)
- ``GET    /tasks/{id}/artifacts``           — list artifacts
- ``GET    /tasks/{id}/approvals``           — list approvals
- ``POST   /tasks/{id}/cancel``              — cancel
- ``POST   /tasks/{id}/pause``               — pause
- ``POST   /tasks/{id}/resume``              — resume
- ``POST   /tasks/{id}/message``             — user→worker message
- ``POST   /approvals/{id}/decide``          — approve/reject
- ``GET    /pools``                          — list pools
- ``POST   /pools``                          — create pool
- ``DELETE /pools/{id}``                     — delete pool
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.workers import service as svc
from ai_portal.workers.events.writer import EventRecord, EventWriter, get_writer
from ai_portal.workers.schemas import (
    ApprovalDecideBody,
    ApprovalOut,
    ArtifactOut,
    CancelReasonBody,
    PoolIn,
    PoolOut,
    RunOut,
    SubmitTaskBody,
    TaskOut,
    UserMessageBody,
)
from ai_portal.workers.types import EventKind

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workers", tags=["workers"])


# ── converters ───────────────────────────────────────────────────


def _task_to_out(t) -> TaskOut:
    return TaskOut(
        id=str(t.id),
        org_id=str(t.org_id),
        pool_id=str(t.pool_id) if t.pool_id else None,
        title=t.title,
        description=t.description or "",
        repo=t.repo,
        base_branch=t.base_branch,
        status=t.status,
        trigger_source=t.trigger_source,
        created_by=t.created_by,
        created_at=t.created_at,
        completed_at=t.completed_at,
    )


def _run_to_out(r) -> RunOut:
    return RunOut(
        id=str(r.id),
        task_id=str(r.task_id),
        attempt_no=r.attempt_no,
        status=r.status,
        started_at=r.started_at,
        ended_at=r.ended_at,
        cost_cents=r.cost_cents,
        error=r.error,
    )


def _pool_to_out(p) -> PoolOut:
    return PoolOut(
        id=str(p.id),
        org_id=str(p.org_id),
        name=p.name,
        template=p.template,
        sandbox_provider=p.sandbox_provider,
        repo_allow_list=list(p.repo_allow_list_json or []),
        budget_cents_per_task=p.budget_cents_per_task,
        default_model=p.default_model,
        settings=dict(p.settings_json or {}),
        enabled=p.enabled,
        created_at=p.created_at,
    )


def _artifact_to_out(a) -> ArtifactOut:
    return ArtifactOut(
        id=str(a.id),
        run_id=str(a.run_id),
        kind=a.kind,
        ref=a.ref,
        meta=dict(a.meta_json or {}),
        created_at=a.created_at,
    )


def _approval_to_out(a) -> ApprovalOut:
    return ApprovalOut(
        id=str(a.id),
        task_id=str(a.task_id),
        kind=a.kind,
        requested_at=a.requested_at,
        decided_at=a.decided_at,
        decided_by=a.decided_by,
        decision=a.decision,
        reason=a.reason,
        required_approvers=a.required_approvers,
    )


# ── dependency: event writer ─────────────────────────────────────


def get_event_writer() -> EventWriter:
    return get_writer()


# ── tasks ────────────────────────────────────────────────────────


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def submit_task(
    body: SubmitTaskBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> TaskOut:
    try:
        pool_uuid = _uuid.UUID(body.pool_id) if body.pool_id else None
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid pool_id")
    try:
        t = svc.submit_task(
            db,
            org_id=org_id,
            pool_id=pool_uuid,
            title=body.title,
            description=body.description,
            repo=body.repo,
            base_branch=body.base_branch,
            trigger_source=body.trigger_source,
            trigger_payload=body.extra,
            created_by=str(user.id) if user else None,
        )
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except svc.WorkersError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return _task_to_out(t)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    pool_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[TaskOut]:
    pool_uuid = _uuid.UUID(pool_id) if pool_id else None
    rows = svc.list_tasks(
        db, org_id=org_id, pool_id=pool_uuid, status_filter=status_filter, limit=limit
    )
    return [_task_to_out(t) for t in rows]


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> TaskOut:
    try:
        t = svc.get_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return _task_to_out(t)


@router.get("/tasks/{task_id}/runs", response_model=list[RunOut])
def list_runs_for_task(
    task_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[RunOut]:
    try:
        svc.get_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return [_run_to_out(r) for r in svc.list_runs(db, task_id=_uuid.UUID(task_id))]


@router.get("/tasks/{task_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts_for_task(
    task_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[ArtifactOut]:
    try:
        svc.get_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return [_artifact_to_out(a) for a in svc.list_artifacts(db, task_id=_uuid.UUID(task_id))]


@router.get("/tasks/{task_id}/approvals", response_model=list[ApprovalOut])
def list_approvals_for_task(
    task_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[ApprovalOut]:
    try:
        svc.get_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return [_approval_to_out(a) for a in svc.list_approvals(db, task_id=_uuid.UUID(task_id))]


# ── controls ────────────────────────────────────────────────────


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(
    task_id: str,
    body: CancelReasonBody | None = None,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    writer: EventWriter = Depends(get_event_writer),
) -> TaskOut:
    try:
        t = svc.cancel_task(db, org_id=org_id, task_id=_uuid.UUID(task_id), reason=body.reason if body else None)
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except svc.IllegalTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    # best-effort: broadcast phase_changed to any live subscribers per run
    for r in svc.list_runs(db, task_id=t.id):
        await writer.emit(str(r.id), EventKind.phase_changed, {"to": "cancelled"})
    return _task_to_out(t)


@router.post("/tasks/{task_id}/pause", response_model=TaskOut)
async def pause_task(
    task_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    writer: EventWriter = Depends(get_event_writer),
) -> TaskOut:
    try:
        t = svc.pause_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except svc.IllegalTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    for r in svc.list_runs(db, task_id=t.id):
        await writer.emit(str(r.id), EventKind.phase_changed, {"to": "paused"})
    return _task_to_out(t)


@router.post("/tasks/{task_id}/resume", response_model=TaskOut)
async def resume_task(
    task_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    writer: EventWriter = Depends(get_event_writer),
) -> TaskOut:
    try:
        t = svc.resume_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except svc.IllegalTransition as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    for r in svc.list_runs(db, task_id=t.id):
        await writer.emit(str(r.id), EventKind.phase_changed, {"to": "executing"})
    return _task_to_out(t)


@router.post("/tasks/{task_id}/message", status_code=status.HTTP_202_ACCEPTED)
async def send_message_to_worker(
    task_id: str,
    body: UserMessageBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    writer: EventWriter = Depends(get_event_writer),
) -> dict:
    try:
        t = svc.get_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    runs = svc.list_runs(db, task_id=t.id)
    payload = {"from": str(user.id) if user else None, "text": body.text}
    for r in runs:
        await writer.emit(str(r.id), EventKind.user_message, payload)
    return {"ok": True, "delivered_to_runs": len(runs)}


# ── approvals ───────────────────────────────────────────────────


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(
    approval_id: str,
    body: ApprovalDecideBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ApprovalOut:
    try:
        row = svc.decide_approval(
            db,
            org_id=org_id,
            approval_id=_uuid.UUID(approval_id),
            decision=body.decision,
            decided_by=str(user.id) if user else None,
            reason=body.reason,
        )
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    db.commit()
    return _approval_to_out(row)


# ── pools ───────────────────────────────────────────────────────


@router.get("/pools", response_model=list[PoolOut])
def list_pools(
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[PoolOut]:
    return [_pool_to_out(p) for p in svc.list_pools(db, org_id=org_id)]


@router.post("/pools", response_model=PoolOut, status_code=status.HTTP_201_CREATED)
def create_pool(
    body: PoolIn,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> PoolOut:
    p = svc.create_pool(
        db,
        org_id=org_id,
        name=body.name,
        template=body.template,
        sandbox_provider=body.sandbox_provider,
        repo_allow_list=body.repo_allow_list,
        budget_cents_per_task=body.budget_cents_per_task,
        default_model=body.default_model,
        settings=body.settings,
        enabled=body.enabled,
    )
    db.commit()
    return _pool_to_out(p)


@router.delete("/pools/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pool(
    pool_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    try:
        svc.delete_pool(db, org_id=org_id, pool_id=_uuid.UUID(pool_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    db.commit()
    return None


# ── SSE events stream ───────────────────────────────────────────


def _sse_pack(rec_id: str, kind: str, payload: dict, ts: datetime) -> str:
    body = {"id": rec_id, "kind": kind, "ts": ts.isoformat(), "payload": payload}
    return f"id: {rec_id}\nevent: {kind}\ndata: {json.dumps(body, default=str)}\n\n"


@router.get("/tasks/{task_id}/events")
async def stream_events(
    task_id: str,
    after_ts: str | None = Query(default=None),
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
    writer: EventWriter = Depends(get_event_writer),
):
    """SSE live stream of worker events.

    Behaviour:

    - Authorises the task via the actor's org.
    - Backfills persisted events (optionally filtered by ``after_ts``).
    - Subscribes to the writer for each run id and streams live events.
    - Emits ``: keepalive`` every 15s of idle to keep the connection alive.
    """
    try:
        task = svc.get_task(db, org_id=org_id, task_id=_uuid.UUID(task_id))
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))

    after_dt: datetime | None = None
    if after_ts:
        try:
            after_dt = datetime.fromisoformat(after_ts.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bad after_ts")

    runs = svc.list_runs(db, task_id=task.id)
    run_ids = [str(r.id) for r in runs]

    queue: asyncio.Queue[EventRecord] = asyncio.Queue()

    async def cb(rec: EventRecord) -> None:
        await queue.put(rec)

    async def gen():
        # Backfill
        try:
            for row in svc.list_events_for_task(db, task_id=task.id, after_ts=after_dt):
                yield _sse_pack(
                    str(row.id), row.kind, row.payload_json or {}, row.ts
                )
        except Exception:  # noqa: BLE001
            log.exception("backfill failed for task %s", task.id)
        # Subscribe + live
        for rid in run_ids:
            writer.subscribe(rid, cb)
        try:
            while True:
                try:
                    rec = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _sse_pack(rec.id, rec.kind, rec.payload, rec.ts)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            return
        finally:
            for rid in run_ids:
                writer.unsubscribe(rid, cb)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
