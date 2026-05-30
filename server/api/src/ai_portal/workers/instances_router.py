"""Worker-instances HTTP API — worker-centric ("a worker IS a task").

Routes (prefix ``/v1/workers``):

- ``POST   /instances``                       — spawn a worker
- ``GET    /instances``                       — list workers
- ``GET    /instances/{id}``                  — get a worker
- ``POST   /instances/{id}/stop``             — stop a worker
- ``GET    /instances/{id}/stream``           — SSE agent stdio (STUB)
- ``POST   /instances/{id}/message``          — user message → starts a run
- ``GET    /instances/{id}/runs``             — list runs
- ``GET    /instances/{id}/messages``         — worker chat thread
- ``GET    /runs/{run_id}/changes``           — changed files + diffs for a run
- ``POST   /instances/{id}/permissions/{prompt_id}`` — allow/deny inline prompt

Separate router from the legacy task-centric :mod:`ai_portal.workers.router`.
Agent execution is stubbed (see instances_service); the stream endpoint emits
a single ``stub`` notice — it does NOT fabricate agent output.
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.workers import instances_service as svc
from ai_portal.workers.schemas import (
    InstanceRunOut,
    PermissionDecideBody,
    RunChangeOut,
    SpawnWorkerBody,
    WorkerChatMessageOut,
    WorkerMessageBody,
    WorkerOut,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workers", tags=["workers"])


# ── converters ───────────────────────────────────────────────────


def _worker_to_out(w) -> WorkerOut:
    return WorkerOut(
        id=str(w.id),
        org_id=str(w.org_id),
        pool_id=str(w.pool_id) if w.pool_id else None,
        name=w.name,
        state=w.state,
        mode=w.mode,
        model=w.model,
        runtime=w.runtime,
        connector=dict(w.connector_json or {}),
        repo_url=w.repo_url,
        sandbox_id=str(w.sandbox_id) if w.sandbox_id else None,
        trigger_source=w.trigger_source,
        created_by=w.created_by,
        created_at=w.created_at,
        last_active_at=w.last_active_at,
    )


def _run_to_out(r) -> InstanceRunOut:
    return InstanceRunOut(
        id=str(r.id),
        worker_id=str(r.worker_id),
        seq_no=r.seq_no,
        user_message=r.user_message,
        status=r.status,
        started_at=r.started_at,
        ended_at=r.ended_at,
        cost_cents=r.cost_cents,
        error=r.error,
    )


def _change_to_out(c) -> RunChangeOut:
    return RunChangeOut(
        id=str(c.id),
        run_id=str(c.run_id),
        file_path=c.file_path,
        change_kind=c.change_kind,
        additions=c.additions,
        deletions=c.deletions,
        diff_ref=c.diff_ref,
    )


def _msg_to_out(m) -> WorkerChatMessageOut:
    return WorkerChatMessageOut(
        id=str(m.id),
        worker_id=str(m.worker_id),
        run_id=str(m.run_id) if m.run_id else None,
        role=m.role,
        content=m.content,
        ts=m.ts,
    )


def _uuid_or_422(raw: str, label: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(raw)
    except (ValueError, TypeError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid {label}"
        )


# ── workers ──────────────────────────────────────────────────────


@router.post(
    "/instances", response_model=WorkerOut, status_code=status.HTTP_201_CREATED
)
def spawn_worker(
    body: SpawnWorkerBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> WorkerOut:
    pool_uuid = _uuid_or_422(body.pool_id, "pool_id") if body.pool_id else None
    try:
        w = svc.spawn_worker(
            db,
            org_id=org_id,
            name=body.name,
            model=body.model,
            mode=body.mode,
            runtime=body.runtime,
            connector=body.connector,
            repo_url=body.repo_url,
            pool_id=pool_uuid,
            skills=body.skills,
            trigger_source=body.trigger_source,
            trigger_payload=body.trigger_payload,
            created_by=str(user.id) if user else None,
        )
    except svc.InvalidArg as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    return _worker_to_out(w)


@router.get("/instances", response_model=list[WorkerOut])
def list_workers(
    state: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[WorkerOut]:
    rows = svc.list_workers(db, org_id=org_id, state=state, limit=limit)
    return [_worker_to_out(w) for w in rows]


@router.get("/instances/{worker_id}", response_model=WorkerOut)
def get_worker(
    worker_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> WorkerOut:
    try:
        w = svc.get_worker(
            db, org_id=org_id, worker_id=_uuid_or_422(worker_id, "worker_id")
        )
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return _worker_to_out(w)


@router.post("/instances/{worker_id}/stop", response_model=WorkerOut)
def stop_worker(
    worker_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> WorkerOut:
    try:
        w = svc.stop_worker(
            db, org_id=org_id, worker_id=_uuid_or_422(worker_id, "worker_id")
        )
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    db.commit()
    return _worker_to_out(w)


# ── message → run ────────────────────────────────────────────────


@router.post(
    "/instances/{worker_id}/message", status_code=status.HTTP_201_CREATED
)
def send_message(
    worker_id: str,
    body: WorkerMessageBody,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> InstanceRunOut:
    """User message → starts a run. Agent work itself is stubbed."""
    try:
        run, _msg = svc.start_run(
            db,
            org_id=org_id,
            worker_id=_uuid_or_422(worker_id, "worker_id"),
            user_message=body.text,
        )
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    except svc.InvalidArg as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    return _run_to_out(run)


@router.get("/instances/{worker_id}/runs", response_model=list[InstanceRunOut])
def list_runs(
    worker_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[InstanceRunOut]:
    wid = _uuid_or_422(worker_id, "worker_id")
    try:
        svc.get_worker(db, org_id=org_id, worker_id=wid)
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return [_run_to_out(r) for r in svc.list_runs(db, worker_id=wid)]


@router.get(
    "/instances/{worker_id}/messages", response_model=list[WorkerChatMessageOut]
)
def list_messages(
    worker_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[WorkerChatMessageOut]:
    wid = _uuid_or_422(worker_id, "worker_id")
    try:
        svc.get_worker(db, org_id=org_id, worker_id=wid)
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return [_msg_to_out(m) for m in svc.list_messages(db, worker_id=wid)]


@router.get("/runs/{run_id}/changes", response_model=list[RunChangeOut])
def list_run_changes(
    run_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[RunChangeOut]:
    rid = _uuid_or_422(run_id, "run_id")
    try:
        run = svc.get_run(db, run_id=rid)
        # authorize via the owning worker's org
        svc.get_worker(db, org_id=org_id, worker_id=run.worker_id)
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return [_change_to_out(c) for c in svc.list_run_changes(db, run_id=rid)]


# ── inline permission prompts ────────────────────────────────────


@router.post("/instances/{worker_id}/permissions/{prompt_id}")
def decide_permission(
    worker_id: str,
    prompt_id: str,
    body: PermissionDecideBody,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> dict:
    """Allow/deny an inline agent-SDK tool-permission prompt.

    STUB: validates the worker + body and acknowledges. Relaying the decision
    to the live runtime (``canUseTool`` responder) needs the in-sandbox runner
    control channel — deferred (TODO agent-sdk-boundary).
    """
    wid = _uuid_or_422(worker_id, "worker_id")
    try:
        svc.get_worker(db, org_id=org_id, worker_id=wid)
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return {
        "ok": True,
        "prompt_id": prompt_id,
        "decision": body.decision,
        "delivered": False,
        "note": "runtime control channel not wired — decision recorded only",
    }


# ── SSE stream (STUB) ────────────────────────────────────────────


@router.get("/instances/{worker_id}/stream")
def stream_agent_stdio(
    worker_id: str,
    db: Session = Depends(get_db),
    org_id: _uuid.UUID = Depends(get_current_org_id),
):
    """SSE stream of the agent's terminal stdio.

    STUB: opens a valid SSE channel and emits one ``stub`` event, then closes.
    Real live streaming requires the in-sandbox runner wire protocol — it does
    NOT fabricate agent output (TODO agent-sdk-boundary).
    """
    wid = _uuid_or_422(worker_id, "worker_id")
    try:
        svc.get_worker(db, org_id=org_id, worker_id=wid)
    except svc.NotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))

    async def gen():
        notice = {
            "kind": "stub",
            "note": (
                "agent runtime not wired — no live stdio. See "
                "workers/agent_runtime/in_sandbox_runner.py"
            ),
        }
        yield f"event: stub\ndata: {json.dumps(notice)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
