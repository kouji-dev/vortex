"""Gateway traces HTTP surface — search, get, replay.

Routes:

- ``GET /v1/gateway/traces?model=...&from=...&to=...&status=...&actor_user_id=...``
  paginates via ``cursor`` (keyset, base64 of ``ts|id``).
- ``GET /v1/gateway/traces/{id}`` — full trace including stored
  ``request_json``.
- ``POST /v1/gateway/traces/{id}/replay?model=...&routing_policy_id=...`` —
  re-dispatch the historic request through the active gateway provider and
  write a new trace row.

Permission gating:

- ``gateway:traces:read`` for ``GET`` routes
- ``gateway:replay`` for the replay ``POST``
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_permission
from ai_portal.gateway import service as gateway_service
from ai_portal.gateway.traces.service import (
    SearchPage,
    TraceDetail,
    TracesService,
    TraceSummary,
)
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/gateway/traces", tags=["gateway-traces"])


# ── schemas ──────────────────────────────────────────────────────────────


class TraceSummaryOut(BaseModel):
    id: str
    actor_json: dict
    route: str
    model_requested: str | None
    model_used: str | None
    provider: str | None
    status: str
    latency_ms: int | None
    ttft_ms: int | None
    tokens_in: int
    tokens_out: int
    tokens_cache_read: int
    tokens_cache_write: int
    cost_cents: float
    cache_hit: bool
    error: str | None
    request_hash: str | None
    ts: datetime


class TraceSearchResponse(BaseModel):
    items: list[TraceSummaryOut]
    next_cursor: str | None


class TraceDetailOut(TraceSummaryOut):
    request_json: dict[str, Any] | None


class ReplayResponse(BaseModel):
    trace_id: str
    model_used: str
    status: str


# ── converters ───────────────────────────────────────────────────────────


def _summary_to_out(s: TraceSummary) -> TraceSummaryOut:
    return TraceSummaryOut(
        id=str(s.id),
        actor_json=s.actor_json,
        route=s.route,
        model_requested=s.model_requested,
        model_used=s.model_used,
        provider=s.provider,
        status=s.status,
        latency_ms=s.latency_ms,
        ttft_ms=s.ttft_ms,
        tokens_in=s.tokens_in,
        tokens_out=s.tokens_out,
        tokens_cache_read=s.tokens_cache_read,
        tokens_cache_write=s.tokens_cache_write,
        cost_cents=s.cost_cents,
        cache_hit=s.cache_hit,
        error=s.error,
        request_hash=s.request_hash,
        ts=s.ts,
    )


# ── routes ───────────────────────────────────────────────────────────────


@router.get("", response_model=TraceSearchResponse)
def search_traces(
    model: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    provider: str | None = Query(None),
    actor_user_id: int | None = Query(None),
    ts_from: datetime | None = Query(None, alias="from"),
    ts_to: datetime | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    actor: Actor = Depends(require_permission("gateway:traces:read")),
    db: Session = Depends(get_db),
) -> TraceSearchResponse:
    """Paginated org-scoped trace search."""
    svc = TracesService(db)
    page: SearchPage = svc.search(
        org_id=actor.org_id,
        model=model,
        status=status_filter,
        provider=provider,
        actor_user_id=actor_user_id,
        ts_from=ts_from,
        ts_to=ts_to,
        limit=limit,
        cursor=cursor,
    )
    return TraceSearchResponse(
        items=[_summary_to_out(s) for s in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{trace_id}", response_model=TraceDetailOut)
def get_trace(
    trace_id: uuid.UUID,
    actor: Actor = Depends(require_permission("gateway:traces:read")),
    db: Session = Depends(get_db),
) -> TraceDetailOut:
    """Full trace including the canonical request JSON."""
    svc = TracesService(db)
    detail: TraceDetail | None = svc.get(org_id=actor.org_id, trace_id=trace_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="trace not found")
    base = _summary_to_out(detail.summary).model_dump()
    return TraceDetailOut(**base, request_json=detail.request_json)


@router.post("/{trace_id}/replay", response_model=ReplayResponse)
async def replay_trace(
    trace_id: uuid.UUID,
    model: str | None = Query(None),
    routing_policy_id: str | None = Query(None),
    actor: Actor = Depends(require_permission("gateway:replay")),
    db: Session = Depends(get_db),
    provider=Depends(gateway_service.get_llm_provider),
) -> ReplayResponse:
    """Re-dispatch a historic request through the active provider.

    Query params:

    - ``model`` — override the model on replay (use canonical / alias name).
    - ``routing_policy_id`` — override the routing policy. Recorded on the
      new request's metadata so downstream routing picks it up.

    Returns the new trace id.
    """
    svc = TracesService(db)
    actor_scope: dict = {}
    if actor.user_id is not None:
        actor_scope["actor_user_id"] = actor.user_id
    if actor.api_key_id is not None:
        actor_scope["api_key_id"] = actor.api_key_id

    new_id = await svc.replay(
        org_id=actor.org_id,
        trace_id=trace_id,
        provider=provider,
        model_override=model,
        routing_policy_id_override=routing_policy_id,
        actor_json=actor_scope,
    )
    if new_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="trace not found or has no stored request body",
        )

    # Read back the new row to surface model_used + status.
    detail = svc.get(org_id=actor.org_id, trace_id=new_id)
    if detail is None:
        # Should not happen — the write just succeeded.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="replay write failed"
        )
    return ReplayResponse(
        trace_id=str(new_id),
        model_used=detail.summary.model_used or (model or ""),
        status=detail.summary.status,
    )


__all__ = ["router"]
