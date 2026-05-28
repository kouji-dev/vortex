"""Memory analytics rollups.

Five series:
- count over time per (type, scope_kind)
- top recalled memories (last N days)
- recall hit-rate (uses linked to responses)
- extraction outcomes (created / dedupe / refused) by memory_jobs.status
- token cost rollup from ``usage_events`` (module=memory)
"""
from __future__ import annotations

import logging
import re
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryJob, MemoryUse

logger = logging.getLogger(__name__)


async def count_by_type_scope(
    session: AsyncSession, org_id: _uuid.UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Memory.type, Memory.scope_kind, func.count(Memory.id))
            .where(Memory.org_id == org_id, Memory.deleted_at.is_(None))
            .group_by(Memory.type, Memory.scope_kind)
        )
    ).all()
    return [
        {"type": t.value, "scope_kind": s.value, "count": int(c)}
        for t, s, c in rows
    ]


async def top_recalled(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    days: int = 30,
    limit: int = 20,
) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        await session.execute(
            select(
                Memory.id,
                Memory.text,
                func.count(MemoryUse.id).label("uses"),
            )
            .join(MemoryUse, MemoryUse.memory_id == Memory.id)
            .where(Memory.org_id == org_id, MemoryUse.ts >= cutoff)
            .group_by(Memory.id, Memory.text)
            .order_by(desc("uses"))
            .limit(limit)
        )
    ).all()
    return [{"memory_id": str(i), "text": t, "uses": int(c)} for i, t, c in rows]


async def recall_hit_rate(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Fraction of recalls that have a linked response message."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    total = int(
        (
            await session.execute(
                select(func.count(MemoryUse.id))
                .join(Memory, Memory.id == MemoryUse.memory_id)
                .where(Memory.org_id == org_id, MemoryUse.ts >= cutoff)
            )
        ).scalar()
        or 0
    )
    linked = int(
        (
            await session.execute(
                select(func.count(MemoryUse.id))
                .join(Memory, Memory.id == MemoryUse.memory_id)
                .where(
                    Memory.org_id == org_id,
                    MemoryUse.ts >= cutoff,
                    MemoryUse.response_message_id != "",
                )
            )
        ).scalar()
        or 0
    )
    return {"total": total, "linked": linked, "rate": (linked / total) if total else 0.0}


async def extraction_outcomes(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    days: int = 30,
) -> dict[str, int]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        await session.execute(
            select(MemoryJob.status, func.count(MemoryJob.id))
            .where(
                MemoryJob.org_id == org_id,
                MemoryJob.kind == "extract",
                MemoryJob.ended_at.is_not(None),
                MemoryJob.ended_at >= cutoff,
            )
            .group_by(MemoryJob.status)
        )
    ).all()
    return {str(s): int(c) for s, c in rows}


async def rollup_all(
    session: AsyncSession, org_id: _uuid.UUID
) -> dict[str, Any]:
    return {
        "count_by_type_scope": await count_by_type_scope(session, org_id),
        "top_recalled": await top_recalled(session, org_id),
        "recall_hit_rate": await recall_hit_rate(session, org_id),
        "extraction_outcomes": await extraction_outcomes(session, org_id),
    }


# ── cost ───────────────────────────────────────────────────────────────────


_TOKEN_UNITS = frozenset({"tokens_in", "tokens_out", "tokens_cache_read", "tokens_cache_write"})

_PERIOD_RE = re.compile(r"^(\d+)([dhw])$")


def parse_period(period: str | None, default_days: int = 30) -> timedelta:
    """Accepts ``30d`` / ``24h`` / ``2w`` shorthand; falls back to default_days."""
    if not period:
        return timedelta(days=default_days)
    m = _PERIOD_RE.match(period.strip().lower())
    if not m:
        return timedelta(days=default_days)
    n, unit = int(m.group(1)), m.group(2)
    if unit == "d":
        return timedelta(days=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "w":
        return timedelta(weeks=n)
    return timedelta(days=default_days)


@dataclass(slots=True)
class MemoryCostBreakdown:
    tokens_in: float = 0.0
    tokens_out: float = 0.0
    tokens_cache_read: float = 0.0
    tokens_cache_write: float = 0.0
    total_tokens: float = 0.0
    total_cost_usd: float = 0.0
    by_model: dict[str, dict[str, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_model is None:
            self.by_model = {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_cache_read": self.tokens_cache_read,
            "tokens_cache_write": self.tokens_cache_write,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "by_model": self.by_model,
        }


def _as_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def aggregate_cost(events: Iterable) -> MemoryCostBreakdown:
    """Bucket memory-module ``usage_events`` rows into a cost breakdown."""
    b = MemoryCostBreakdown()
    for ev in events:
        unit = getattr(ev, "unit", None) or ""
        if unit not in _TOKEN_UNITS:
            continue
        qty = _as_float(getattr(ev, "qty", 0.0))
        cost = _as_float(getattr(ev, "cost_usd", 0.0))
        model = getattr(ev, "model", None) or "unknown"
        if unit == "tokens_in":
            b.tokens_in += qty
        elif unit == "tokens_out":
            b.tokens_out += qty
        elif unit == "tokens_cache_read":
            b.tokens_cache_read += qty
        elif unit == "tokens_cache_write":
            b.tokens_cache_write += qty
        b.total_tokens += qty
        b.total_cost_usd += cost
        slot = b.by_model.setdefault(
            model, {"tokens": 0.0, "cost_usd": 0.0}
        )
        slot["tokens"] += qty
        slot["cost_usd"] += cost
    return b


async def extraction_token_cost(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    period: str | None = "30d",
) -> dict[str, Any]:
    """Sum ``usage_events`` for ``module='memory'`` over the given period.

    Returns the same shape as :func:`aggregate_cost` plus a ``period`` echo.
    """
    from ai_portal.usage.events_model import UsageEvent

    delta = parse_period(period)
    cutoff = datetime.utcnow() - delta
    rows = (
        await session.execute(
            select(UsageEvent).where(
                UsageEvent.org_id == org_id,
                UsageEvent.module == "memory",
                UsageEvent.ts >= cutoff,
            )
        )
    ).scalars().all()
    breakdown = aggregate_cost(rows)
    out = breakdown.as_dict()
    out["period"] = period or "30d"
    out["since"] = cutoff.isoformat()
    return out
