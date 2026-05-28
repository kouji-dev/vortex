"""Playground HTTP surface.

Routes:

- ``GET    /v1/gateway/playground/sessions``      — list saved snapshots
- ``POST   /v1/gateway/playground/sessions``      — save a new snapshot
- ``GET    /v1/gateway/playground/sessions/{id}`` — fetch one snapshot
- ``DELETE /v1/gateway/playground/sessions/{id}`` — delete a snapshot
- ``POST   /v1/gateway/playground/run``           — execute a snapshot through
  the gateway facade against one or more models and return outputs +
  cost + latency.

The service is resolved through :func:`get_playground_service` so tests can
override it via ``app.dependency_overrides``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_actor
from ai_portal.gateway.playground.schemas import (
    RunRequest,
    RunResponse,
    SessionCreate,
    SessionOut,
)
from ai_portal.gateway.playground.service import PlaygroundService, SessionView
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/gateway/playground", tags=["gateway-playground"])


def get_playground_service(db: Session = Depends(get_db)) -> PlaygroundService:
    """FastAPI dep returning the service. Overridable in tests."""
    return PlaygroundService(db)


def _to_out(v: SessionView) -> SessionOut:
    return SessionOut(
        id=str(v.id),
        name=v.name,
        snapshot=v.snapshot,
        created_at=v.created_at,  # type: ignore[arg-type]
        updated_at=v.updated_at,  # type: ignore[arg-type]
    )


# ── routes ───────────────────────────────────────────────────────────────


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    actor: Actor = Depends(require_actor),
    svc: PlaygroundService = Depends(get_playground_service),
) -> list[SessionOut]:
    views = svc.list_sessions(org_id=actor.org_id, user_id=actor.user_id)
    return [_to_out(v) for v in views]


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    body: SessionCreate,
    actor: Actor = Depends(require_actor),
    svc: PlaygroundService = Depends(get_playground_service),
) -> SessionOut:
    view = svc.create_session(
        org_id=actor.org_id,
        user_id=actor.user_id,
        name=body.name,
        snapshot=body.snapshot,
    )
    return _to_out(view)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    svc: PlaygroundService = Depends(get_playground_service),
) -> SessionOut:
    view = svc.get_session(org_id=actor.org_id, session_id=session_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    return _to_out(view)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    svc: PlaygroundService = Depends(get_playground_service),
) -> None:
    ok = svc.delete_session(org_id=actor.org_id, session_id=session_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")


@router.post("/run", response_model=RunResponse)
async def run_snapshot(
    body: RunRequest,
    actor: Actor = Depends(require_actor),
    svc: PlaygroundService = Depends(get_playground_service),
) -> RunResponse:
    snapshot = body.model_dump(exclude_none=True)
    results = await svc.run_snapshot(
        org_id=actor.org_id,
        user_id=actor.user_id,
        snapshot=snapshot,
    )
    return RunResponse(results=results)


__all__ = ["get_playground_service", "router"]
