"""Gateway observability dashboard endpoints.

Three GETs under ``/v1/gateway/metrics``:

- ``GET /v1/gateway/metrics/top-spenders?period=24h&limit=10``
- ``GET /v1/gateway/metrics/top-errors?period=24h&limit=10``
- ``GET /v1/gateway/metrics/latency?period=24h``

All org-scoped via the active ``Actor``. Period in {1h, 24h, 7d, 30d}.
Requires ``gateway:traces:read``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_permission
from ai_portal.gateway.traces.metrics import (
    ErrorRow,
    LatencyRow,
    MetricsService,
    SpenderRow,
    period_to_delta,
)
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/gateway/metrics", tags=["gateway-metrics"])


# ── schemas ──────────────────────────────────────────────────────────────


class SpenderOut(BaseModel):
    actor_key: str
    actor_user_id: int | None
    api_key_id: str | None
    cost_cents: float
    request_count: int
    tokens_in: int
    tokens_out: int


class ErrorOut(BaseModel):
    error: str
    provider: str | None
    count: int


class LatencyOut(BaseModel):
    provider: str | None
    p50_ms: int | None
    p95_ms: int | None
    p99_ms: int | None
    request_count: int


class TopSpendersResponse(BaseModel):
    period: str
    items: list[SpenderOut]


class TopErrorsResponse(BaseModel):
    period: str
    items: list[ErrorOut]


class LatencyResponse(BaseModel):
    period: str
    items: list[LatencyOut]


# ── helpers ──────────────────────────────────────────────────────────────


def _validate_period(period: str) -> str:
    try:
        period_to_delta(period)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return period


def _spender_out(r: SpenderRow) -> SpenderOut:
    return SpenderOut(
        actor_key=r.actor_key,
        actor_user_id=r.actor_user_id,
        api_key_id=r.api_key_id,
        cost_cents=r.cost_cents,
        request_count=r.request_count,
        tokens_in=r.tokens_in,
        tokens_out=r.tokens_out,
    )


def _error_out(r: ErrorRow) -> ErrorOut:
    return ErrorOut(error=r.error, provider=r.provider, count=r.count)


def _latency_out(r: LatencyRow) -> LatencyOut:
    return LatencyOut(
        provider=r.provider,
        p50_ms=r.p50_ms,
        p95_ms=r.p95_ms,
        p99_ms=r.p99_ms,
        request_count=r.request_count,
    )


# ── routes ───────────────────────────────────────────────────────────────


@router.get("/top-spenders", response_model=TopSpendersResponse)
def top_spenders(
    period: str = Query("24h"),
    limit: int = Query(10, ge=1, le=200),
    actor: Actor = Depends(require_permission("gateway:traces:read")),
    db: Session = Depends(get_db),
) -> TopSpendersResponse:
    """Top cost spenders for the org in the given period."""
    p = _validate_period(period)
    svc = MetricsService(db)
    items = svc.top_spenders(org_id=actor.org_id, period=p, limit=limit)
    return TopSpendersResponse(period=p, items=[_spender_out(r) for r in items])


@router.get("/top-errors", response_model=TopErrorsResponse)
def top_errors(
    period: str = Query("24h"),
    limit: int = Query(10, ge=1, le=200),
    actor: Actor = Depends(require_permission("gateway:traces:read")),
    db: Session = Depends(get_db),
) -> TopErrorsResponse:
    """Top errors grouped by (error_text, provider) in the period."""
    p = _validate_period(period)
    svc = MetricsService(db)
    items = svc.top_errors(org_id=actor.org_id, period=p, limit=limit)
    return TopErrorsResponse(period=p, items=[_error_out(r) for r in items])


@router.get("/latency", response_model=LatencyResponse)
def latency(
    period: str = Query("24h"),
    actor: Actor = Depends(require_permission("gateway:traces:read")),
    db: Session = Depends(get_db),
) -> LatencyResponse:
    """Per-provider latency percentiles (p50 / p95 / p99) in ms."""
    p = _validate_period(period)
    svc = MetricsService(db)
    items = svc.latency_summary(org_id=actor.org_id, period=p)
    return LatencyResponse(period=p, items=[_latency_out(r) for r in items])


__all__ = ["router"]
