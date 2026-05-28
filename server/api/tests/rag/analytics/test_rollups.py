"""Pure-function rollups — no DB needed.

We construct lightweight stand-ins for ``KbQuery``/``KbFeedback`` rows using
``types.SimpleNamespace`` so the aggregator functions can be exercised
without spinning up SQLAlchemy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ai_portal.rag.analytics.rollups import (
    compute_citation_hit_rate,
    compute_cost_series,
    compute_feedback_breakdown,
    compute_query_stats,
    compute_zero_result,
)


def _q(
    query: str,
    *,
    hits: int = 1,
    citations: list[dict] | None = None,
    latency: int = 100,
    cost: float = 0.01,
    ts: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        query=query,
        hits_count=hits,
        citations_json=citations or [],
        latency_ms=latency,
        cost_cents=cost,
        created_at=ts or datetime.now(timezone.utc),
    )


def _f(rating: str) -> SimpleNamespace:
    return SimpleNamespace(rating=rating, created_at=datetime.now(timezone.utc))


def test_compute_query_stats_groups_by_normalised_text() -> None:
    rows = [
        _q("What is RAG?"),
        _q("  what  is  rag? "),
        _q("Other thing"),
    ]
    stats = compute_query_stats(rows, limit=5)
    assert stats[0].count == 2
    assert stats[0].query.lower().startswith("what is rag")
    assert stats[1].count == 1


def test_compute_query_stats_avg_hits_and_latency() -> None:
    rows = [
        _q("alpha", hits=4, latency=100),
        _q("alpha", hits=8, latency=200),
    ]
    stats = compute_query_stats(rows)
    assert stats[0].avg_hits == 6.0
    assert stats[0].avg_latency_ms == 150.0


def test_compute_zero_result_filters_only_zero_hits() -> None:
    rows = [
        _q("alpha", hits=0),
        _q("alpha", hits=0),
        _q("beta", hits=3),
    ]
    zero = compute_zero_result(rows)
    assert len(zero) == 1
    assert zero[0].query == "alpha"
    assert zero[0].count == 2


def test_compute_citation_hit_rate() -> None:
    rows = [
        _q("q1", citations=[{"document_id": "d1"}, {"document_id": "d2"}]),
        _q("q2", citations=[{"document_id": "d1"}]),
        _q("q3", citations=[]),
    ]
    cite = compute_citation_hit_rate(rows)
    d1 = next(c for c in cite if c.document_id == "d1")
    d2 = next(c for c in cite if c.document_id == "d2")
    assert d1.citations == 2
    assert d1.queries == 3
    assert round(d1.rate, 4) == round(2 / 3, 4)
    assert d2.citations == 1


def test_compute_feedback_breakdown() -> None:
    rows = [_f("up"), _f("up"), _f("up"), _f("down")]
    fb = compute_feedback_breakdown(rows)
    assert fb.up == 3
    assert fb.down == 1
    assert round(fb.ratio, 2) == 0.75


def test_compute_feedback_breakdown_empty_is_zero() -> None:
    assert compute_feedback_breakdown([]).ratio == 0.0


def test_compute_cost_series_buckets_by_day() -> None:
    base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _q("a", cost=2.0, ts=base),
        _q("b", cost=3.0, ts=base + timedelta(hours=1)),
        _q("c", cost=4.0, ts=base + timedelta(days=1)),
    ]
    series = compute_cost_series(rows)
    assert series.granularity == "day"
    assert series.total_cents == 9.0
    by_bucket = {p.bucket: p for p in series.points}
    assert by_bucket["2026-05-01"].cost_cents == 5.0
    assert by_bucket["2026-05-01"].queries == 2
    assert by_bucket["2026-05-02"].cost_cents == 4.0


def test_compute_query_stats_drops_empty_query() -> None:
    rows = [_q(""), _q("   "), _q("x")]
    stats = compute_query_stats(rows)
    assert len(stats) == 1
    assert stats[0].query == "x"
