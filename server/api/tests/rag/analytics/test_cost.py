"""Cost-breakdown aggregator unit tests.

Uses ``SimpleNamespace`` stand-ins for ``UsageEvent`` rows so the aggregator
can be exercised without a database. The DB-backed ``fetch_kb_cost_breakdown``
is covered by integration-level wiring elsewhere; here we lock the pure
bucketing rules.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from ai_portal.rag.analytics.cost import (
    CostBreakdown,
    aggregate_cost_breakdown,
    to_out,
)


def _ev(unit: str, *, cost: float | Decimal, qty: float | Decimal = 0.0):
    return SimpleNamespace(unit=unit, cost_usd=Decimal(str(cost)), qty=Decimal(str(qty)))


def test_empty_events_returns_zero_breakdown() -> None:
    b = aggregate_cost_breakdown([])
    assert b == CostBreakdown()
    assert b.total_cost_usd == 0.0


def test_aggregate_buckets_tokens_storage_query_other() -> None:
    rows = [
        _ev("tokens_in", cost=0.10, qty=1000),
        _ev("tokens_out", cost=0.20, qty=500),
        _ev("tokens_cache_read", cost=0.01, qty=100),
        _ev("tokens_cache_write", cost=0.02, qty=100),
        _ev("storage_gb", cost=0.03, qty=2.0),
        _ev("embeddings", cost=0.04, qty=2000),
        _ev("documents_ingested", cost=0.00, qty=5),
        _ev("queries", cost=0.05, qty=10),
        _ev("worker_minutes", cost=0.99, qty=30),
    ]
    b = aggregate_cost_breakdown(rows)
    assert round(b.tokens_cost_usd, 4) == 0.33
    assert round(b.tokens_qty, 4) == 1700.0
    assert round(b.storage_cost_usd, 4) == 0.07
    assert round(b.storage_qty, 4) == 2007.0
    assert round(b.query_cost_usd, 4) == 0.05
    assert round(b.query_qty, 4) == 10.0
    assert round(b.other_cost_usd, 4) == 0.99
    assert round(b.total_cost_usd, 4) == round(0.33 + 0.07 + 0.05 + 0.99, 4)


def test_aggregate_ten_events_sums_total() -> None:
    """10 fake events → aggregated correctly. (Mirrors task acceptance criteria.)"""
    rows = [_ev("tokens_in", cost=0.001, qty=10) for _ in range(10)]
    b = aggregate_cost_breakdown(rows)
    assert round(b.tokens_cost_usd, 4) == 0.01
    assert round(b.total_cost_usd, 4) == 0.01
    assert b.tokens_qty == 100.0


def test_unknown_unit_falls_into_other() -> None:
    rows = [_ev("mystery_unit", cost=1.23, qty=7)]
    b = aggregate_cost_breakdown(rows)
    assert b.other_cost_usd == 1.23
    assert b.tokens_cost_usd == 0.0


def test_to_out_round_trip() -> None:
    b = aggregate_cost_breakdown(
        [
            _ev("tokens_in", cost=Decimal("0.5"), qty=Decimal("100")),
            _ev("storage_gb", cost=Decimal("0.25"), qty=Decimal("3.5")),
        ]
    )
    out = to_out(b)
    assert out.tokens_cost_usd == 0.5
    assert out.storage_cost_usd == 0.25
    assert out.total_cost_usd == 0.75
    assert out.tokens_qty == 100.0
    assert out.storage_qty == 3.5


def test_missing_attributes_default_to_zero() -> None:
    rows = [SimpleNamespace()]
    b = aggregate_cost_breakdown(rows)
    assert b.total_cost_usd == 0.0


def test_none_cost_skipped_cleanly() -> None:
    rows = [SimpleNamespace(unit="tokens_in", cost_usd=None, qty=None)]
    b = aggregate_cost_breakdown(rows)
    assert b.total_cost_usd == 0.0
