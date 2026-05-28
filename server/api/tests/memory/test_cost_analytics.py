"""Phase Polish-T4 — extraction token-cost analytics."""
from __future__ import annotations

import inspect
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_portal.memory import analytics


def _ev(unit, qty, cost, model="claude-sonnet-4-6"):
    return SimpleNamespace(
        unit=unit, qty=qty, cost_usd=Decimal(str(cost)), model=model
    )


def test_parse_period_default() -> None:
    assert analytics.parse_period(None) == timedelta(days=30)
    assert analytics.parse_period("") == timedelta(days=30)


def test_parse_period_units() -> None:
    assert analytics.parse_period("7d") == timedelta(days=7)
    assert analytics.parse_period("24h") == timedelta(hours=24)
    assert analytics.parse_period("2w") == timedelta(weeks=2)


def test_parse_period_bad_input_falls_back() -> None:
    assert analytics.parse_period("xyz") == timedelta(days=30)
    assert analytics.parse_period("10y", default_days=7) == timedelta(days=7)


def test_aggregate_cost_ignores_non_token_units() -> None:
    evs = [_ev("queries", 5, 0.5), _ev("storage_gb", 1, 0.1)]
    out = analytics.aggregate_cost(evs)
    assert out.total_tokens == 0
    assert out.total_cost_usd == 0


def test_aggregate_cost_buckets_by_unit() -> None:
    evs = [
        _ev("tokens_in", 100, 0.01),
        _ev("tokens_out", 200, 0.02),
        _ev("tokens_cache_read", 50, 0.001),
        _ev("tokens_cache_write", 80, 0.005),
    ]
    out = analytics.aggregate_cost(evs)
    assert out.tokens_in == 100
    assert out.tokens_out == 200
    assert out.tokens_cache_read == 50
    assert out.tokens_cache_write == 80
    assert out.total_tokens == 430
    assert round(out.total_cost_usd, 4) == 0.036


def test_aggregate_cost_by_model() -> None:
    evs = [
        _ev("tokens_in", 100, 0.01, model="a"),
        _ev("tokens_out", 50, 0.005, model="a"),
        _ev("tokens_in", 200, 0.02, model="b"),
    ]
    out = analytics.aggregate_cost(evs)
    assert out.by_model["a"]["tokens"] == 150
    assert round(out.by_model["a"]["cost_usd"], 4) == 0.015
    assert out.by_model["b"]["tokens"] == 200


def test_aggregate_cost_handles_none_model() -> None:
    evs = [_ev("tokens_in", 1, 0.001, model=None)]
    out = analytics.aggregate_cost(evs)
    assert "unknown" in out.by_model


def test_as_dict_shape() -> None:
    out = analytics.aggregate_cost([_ev("tokens_in", 10, 0.01)])
    d = out.as_dict()
    for k in (
        "tokens_in",
        "tokens_out",
        "tokens_cache_read",
        "tokens_cache_write",
        "total_tokens",
        "total_cost_usd",
        "by_model",
    ):
        assert k in d


def test_extraction_token_cost_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(analytics.extraction_token_cost)


def test_router_exposes_cost_endpoint() -> None:
    from ai_portal.memory.v1_router import router

    paths = {r.path for r in router.routes}
    assert "/v1/memories/analytics/cost" in paths


@pytest.mark.asyncio
async def test_extraction_token_cost_empty(monkeypatch) -> None:
    import uuid

    class _Result:
        def scalars(self_):
            return self_

        def all(self_):
            return []

    class _S:
        async def execute(self_, *_a, **_k):
            return _Result()

    out = await analytics.extraction_token_cost(_S(), uuid.uuid4(), period="7d")
    assert out["total_tokens"] == 0
    assert out["period"] == "7d"
    assert "since" in out
