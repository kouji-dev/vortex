"""Gateway observability metrics — aggregations over ``request_traces``.

Three dashboards (period-bucketed; period in {1h, 24h, 7d, 30d}):

- :func:`top_spenders` — sum(cost_cents) grouped by actor.
- :func:`top_errors` — count(*) grouped by error_kind + provider where
  status='error'.
- :func:`latency_summary` — p50 / p95 / p99 per provider.

The service is HTTP-free so the router + tests can share it. Org scope is
**always** enforced; callers pass ``org_id`` explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from ai_portal.gateway.traces.model import RequestTrace

Period = Literal["1h", "24h", "7d", "30d"]

_PERIOD_DELTAS: dict[Period, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def period_to_delta(period: str) -> timedelta:
    """Convert a period string to a ``timedelta``. Raises ``ValueError``."""
    if period not in _PERIOD_DELTAS:
        valid = ", ".join(_PERIOD_DELTAS)
        raise ValueError(f"invalid period '{period}' — expected one of: {valid}")
    return _PERIOD_DELTAS[period]  # type: ignore[index]


def _since(period: str, *, now: datetime | None = None) -> datetime:
    base = now or datetime.now(UTC)
    return base - period_to_delta(period)


# ── DTOs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpenderRow:
    """One row of the top-spenders aggregation."""

    actor_key: str  # "user:<id>" or "api_key:<id>" or "unknown"
    actor_user_id: int | None
    api_key_id: str | None
    cost_cents: float
    request_count: int
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class ErrorRow:
    error: str  # error text (or "unknown" if null)
    provider: str | None
    count: int


@dataclass(frozen=True)
class LatencyRow:
    provider: str | None
    p50_ms: int | None
    p95_ms: int | None
    p99_ms: int | None
    request_count: int


# ── service ──────────────────────────────────────────────────────────────


class MetricsService:
    """Aggregations for the observability dashboards.

    All methods filter by ``org_id`` + period. Empty result lists are valid.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── top spenders ────────────────────────────────────────────────────

    def top_spenders(
        self,
        *,
        org_id: UUID,
        period: str = "24h",
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[SpenderRow]:
        """Aggregate cost by actor over the period. Sorted by cost desc."""
        limit = max(1, min(int(limit), 200))
        since = _since(period, now=now)

        user_key = RequestTrace.actor_json["actor_user_id"].astext
        api_key = RequestTrace.actor_json["api_key_id"].astext

        actor_key_expr = case(
            (user_key.is_not(None), func.concat("user:", user_key)),
            (api_key.is_not(None), func.concat("api_key:", api_key)),
            else_="unknown",
        )

        q = (
            select(
                actor_key_expr.label("actor_key"),
                user_key.label("user_id"),
                api_key.label("api_key_id"),
                func.coalesce(func.sum(RequestTrace.cost_cents), 0).label("cost"),
                func.count().label("n"),
                func.coalesce(func.sum(RequestTrace.tokens_in), 0).label("tokens_in"),
                func.coalesce(func.sum(RequestTrace.tokens_out), 0).label("tokens_out"),
            )
            .where(RequestTrace.org_id == org_id)
            .where(RequestTrace.ts >= since)
            .group_by(actor_key_expr, user_key, api_key)
            .order_by(desc("cost"))
            .limit(limit)
        )

        rows = self.db.execute(q).all()
        out: list[SpenderRow] = []
        for r in rows:
            uid = r.user_id
            kid = r.api_key_id
            out.append(
                SpenderRow(
                    actor_key=r.actor_key or "unknown",
                    actor_user_id=int(uid) if uid and uid.isdigit() else None,
                    api_key_id=kid if kid else None,
                    cost_cents=float(r.cost or 0),
                    request_count=int(r.n),
                    tokens_in=int(r.tokens_in or 0),
                    tokens_out=int(r.tokens_out or 0),
                )
            )
        return out

    # ── top errors ──────────────────────────────────────────────────────

    def top_errors(
        self,
        *,
        org_id: UUID,
        period: str = "24h",
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[ErrorRow]:
        """Count error-status rows grouped by ``(error, provider)``."""
        limit = max(1, min(int(limit), 200))
        since = _since(period, now=now)

        error_key = func.coalesce(RequestTrace.error, "unknown")

        q = (
            select(
                error_key.label("err"),
                RequestTrace.provider.label("prov"),
                func.count().label("n"),
            )
            .where(RequestTrace.org_id == org_id)
            .where(RequestTrace.ts >= since)
            .where(RequestTrace.status == "error")
            .group_by(error_key, RequestTrace.provider)
            .order_by(desc("n"))
            .limit(limit)
        )
        rows = self.db.execute(q).all()
        return [
            ErrorRow(error=str(r.err), provider=r.prov, count=int(r.n))
            for r in rows
        ]

    # ── latency ─────────────────────────────────────────────────────────

    def latency_summary(
        self,
        *,
        org_id: UUID,
        period: str = "24h",
        now: datetime | None = None,
    ) -> list[LatencyRow]:
        """Per-provider p50/p95/p99 latency in ms. NULL latency rows skipped."""
        since = _since(period, now=now)

        # percentile_cont aggregates require ordered-set syntax in
        # SQLAlchemy. ``within_group`` provides it.
        p50 = func.percentile_cont(0.5).within_group(
            RequestTrace.latency_ms.asc()
        )
        p95 = func.percentile_cont(0.95).within_group(
            RequestTrace.latency_ms.asc()
        )
        p99 = func.percentile_cont(0.99).within_group(
            RequestTrace.latency_ms.asc()
        )

        q = (
            select(
                RequestTrace.provider.label("prov"),
                p50.label("p50"),
                p95.label("p95"),
                p99.label("p99"),
                func.count().label("n"),
            )
            .where(RequestTrace.org_id == org_id)
            .where(RequestTrace.ts >= since)
            .where(RequestTrace.latency_ms.is_not(None))
            .group_by(RequestTrace.provider)
            .order_by(desc("n"))
        )
        rows = self.db.execute(q).all()
        return [
            LatencyRow(
                provider=r.prov,
                p50_ms=int(r.p50) if r.p50 is not None else None,
                p95_ms=int(r.p95) if r.p95 is not None else None,
                p99_ms=int(r.p99) if r.p99 is not None else None,
                request_count=int(r.n),
            )
            for r in rows
        ]


__all__ = [
    "ErrorRow",
    "LatencyRow",
    "MetricsService",
    "Period",
    "SpenderRow",
    "period_to_delta",
]
