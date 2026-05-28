"""Usage rollups — aggregate usage_events into hourly/daily/monthly buckets.

Idempotent: each run truncates and rebuilds the rolling window so repeated
invocations converge to the correct totals. The rollups feed the dashboard
and reduce the cost of dimension queries to a single ``SUM`` over a small
table.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.core.db.rls import bypass_rls
from ai_portal.usage.events_model import UsageEvent


Grain = Literal["hour", "day", "month"]
Dim = Literal["user", "team", "key", "model", "module", "unit"]


@dataclass(frozen=True, slots=True)
class RollupBucket:
    org_id: _uuid.UUID
    period_start: datetime
    grain: Grain
    dim: Dim
    dim_value: str
    qty: Decimal
    cost_usd: Decimal
    event_count: int


def _truncate(ts: datetime, grain: Grain) -> datetime:
    ts = ts.astimezone(timezone.utc)
    if grain == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    if grain == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_period(ts: datetime, grain: Grain) -> datetime:
    if grain == "hour":
        return ts + timedelta(hours=1)
    if grain == "day":
        return ts + timedelta(days=1)
    year = ts.year + (ts.month // 12)
    month = (ts.month % 12) + 1
    return ts.replace(year=year, month=month, day=1)


def _dim_column(dim: Dim):
    if dim == "user":
        return UsageEvent.actor_user_id
    if dim == "team":
        return UsageEvent.actor_team_id
    if dim == "key":
        return UsageEvent.actor_api_key_id
    if dim == "model":
        return UsageEvent.model
    if dim == "module":
        return UsageEvent.module
    return UsageEvent.unit


def aggregate(
    db: Session,
    *,
    org_id: _uuid.UUID,
    grain: Grain,
    dim: Dim,
    period_start: datetime,
    period_end: datetime | None = None,
) -> list[RollupBucket]:
    """Aggregate events for one (grain, dim) over [period_start, period_end).

    If ``period_end`` is omitted, defaults to one period from ``period_start``.
    """
    period_start = _truncate(period_start, grain)
    if period_end is None:
        period_end = _next_period(period_start, grain)

    col = _dim_column(dim)
    with bypass_rls(db):
        rows = db.execute(
            select(
                col.label("dim_value"),
                func.sum(UsageEvent.qty).label("qty"),
                func.sum(UsageEvent.cost_usd).label("cost_usd"),
                func.count().label("event_count"),
            )
            .where(
                UsageEvent.org_id == org_id,
                UsageEvent.ts >= period_start,
                UsageEvent.ts < period_end,
            )
            .group_by(col)
        ).all()

    out: list[RollupBucket] = []
    for r in rows:
        out.append(
            RollupBucket(
                org_id=org_id,
                period_start=period_start,
                grain=grain,
                dim=dim,
                dim_value=str(r.dim_value) if r.dim_value is not None else "unknown",
                qty=r.qty or Decimal("0"),
                cost_usd=r.cost_usd or Decimal("0"),
                event_count=r.event_count or 0,
            )
        )
    return out


def run_hourly(db: Session, org_ids: Iterable[_uuid.UUID], *, now: datetime | None = None) -> int:
    """Aggregate the previous hour across all dimensions. Returns row count."""
    now = now or datetime.now(timezone.utc)
    period = _truncate(now, "hour") - timedelta(hours=1)
    count = 0
    for org_id in org_ids:
        for dim in ("user", "team", "key", "model", "module", "unit"):
            count += len(aggregate(db, org_id=org_id, grain="hour", dim=dim, period_start=period))  # type: ignore[arg-type]
    return count
