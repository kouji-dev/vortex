"""Per-KB cost dashboard aggregation over ``usage_events``.

Sums token, storage, and query unit costs into a single breakdown for a
knowledge base. Filters by ``module="rag"`` + ``resource_kind="kb"`` +
``resource_id=str(kb_id)``. Pure-ish: takes a sequence of UsageEvent rows
(or stand-ins) so it can be unit-tested without a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.rag.analytics.schemas import CostBreakdownOut


_TOKEN_UNITS = frozenset(
    {"tokens_in", "tokens_out", "tokens_cache_read", "tokens_cache_write"}
)
_STORAGE_UNITS = frozenset({"storage_gb", "embeddings", "documents_ingested"})
_QUERY_UNITS = frozenset({"queries"})


@dataclass(slots=True)
class CostBreakdown:
    tokens_cost_usd: float = 0.0
    storage_cost_usd: float = 0.0
    query_cost_usd: float = 0.0
    other_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    tokens_qty: float = 0.0
    storage_qty: float = 0.0
    query_qty: float = 0.0


def _as_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def aggregate_cost_breakdown(events: Iterable) -> CostBreakdown:
    """Bucket each event into tokens/storage/query/other and sum cost+qty."""
    b = CostBreakdown()
    for ev in events:
        unit = getattr(ev, "unit", None) or ""
        cost = _as_float(getattr(ev, "cost_usd", 0.0))
        qty = _as_float(getattr(ev, "qty", 0.0))
        if unit in _TOKEN_UNITS:
            b.tokens_cost_usd += cost
            b.tokens_qty += qty
        elif unit in _STORAGE_UNITS:
            b.storage_cost_usd += cost
            b.storage_qty += qty
        elif unit in _QUERY_UNITS:
            b.query_cost_usd += cost
            b.query_qty += qty
        else:
            b.other_cost_usd += cost
        b.total_cost_usd += cost
    return b


def fetch_kb_cost_breakdown(
    db: Session,
    *,
    kb_id: int,
    since=None,
) -> CostBreakdown:
    """Pull usage_events scoped to a KB and aggregate them."""
    from ai_portal.usage.events_model import UsageEvent

    stmt = select(UsageEvent).where(
        UsageEvent.module == "rag",
        UsageEvent.resource_kind == "kb",
        UsageEvent.resource_id == str(kb_id),
    )
    if since is not None:
        stmt = stmt.where(UsageEvent.ts >= since)
    rows = list(db.scalars(stmt))
    return aggregate_cost_breakdown(rows)


def to_out(b: CostBreakdown) -> CostBreakdownOut:
    return CostBreakdownOut(
        tokens_cost_usd=b.tokens_cost_usd,
        storage_cost_usd=b.storage_cost_usd,
        query_cost_usd=b.query_cost_usd,
        other_cost_usd=b.other_cost_usd,
        total_cost_usd=b.total_cost_usd,
        tokens_qty=b.tokens_qty,
        storage_qty=b.storage_qty,
        query_qty=b.query_qty,
    )


__all__ = [
    "CostBreakdown",
    "CostBreakdownOut",
    "aggregate_cost_breakdown",
    "fetch_kb_cost_breakdown",
    "to_out",
]
