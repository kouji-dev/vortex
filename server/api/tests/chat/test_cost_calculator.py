from decimal import Decimal

import pytest

from ai_portal.chat.cost_calculator import (
    compute_llm_cost,
    compute_tool_cost,
    compute_server_tool_cost,
    CostResult,
)
from ai_portal.chat.tool_outcome import ToolCallOutcome


def test_llm_cost_known_model():
    r = compute_llm_cost(
        model="gpt-4o",
        input_tokens=1_000_000, output_tokens=1_000_000,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
    )
    assert r.estimated is False
    assert r.source == "flat_rate"
    assert r.cost_usd > Decimal("0")


def test_llm_cost_unknown_model_returns_zero_flag_unknown():
    r = compute_llm_cost(
        model="nonexistent-zzz",
        input_tokens=1000, output_tokens=2000,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
    )
    assert r.cost_usd == Decimal("0")
    assert r.estimated is True
    assert r.source == "unknown_model"


def test_tool_cost_prefers_metered_signal():
    # ToolCallOutcome requires result_snippet or error; use error to satisfy validator
    outcome = ToolCallOutcome(
        call_id="c", tool_name="scrape", provider="firecrawl",
        input={}, cost_usd=Decimal("0.017"), error="n/a",
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0.017")
    assert r.estimated is False
    assert r.source == "provider_metered"


def test_tool_cost_falls_back_to_flat_rate():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="scrape", provider="firecrawl", input={},
        result_snippet="ok",
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0.002")
    assert r.estimated is True
    assert r.source == "flat_rate"


def test_tool_cost_free_provider():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="search", provider="duckduckgo", input={},
        result_snippet="ok",
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0")
    assert r.source == "free"


def test_tool_cost_unknown_provider():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="scrape", provider="unknown_provider", input={},
        result_snippet="ok",
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0")
    assert r.source == "unknown_model"


def test_server_tool_uses_llm_rate_only_when_metered_absent():
    r = compute_server_tool_cost(
        tool_name="web_search", provider="anthropic",
        usage_metadata={"search_queries": 2},
    )
    assert r.source in {"free", "flat_rate"}


def test_llm_cost_arithmetic():
    # gpt-4o: input=$2.50/M, output=$10.00/M, cached=$1.25/M, no cache_creation, no reasoning
    # 500K billable input (1M total - 500K cached) + 500K cached + 1M output
    r = compute_llm_cost(
        model="gpt-4o",
        input_tokens=1_000_000, output_tokens=1_000_000,
        cached_input_tokens=500_000, cache_creation_input_tokens=0, reasoning_tokens=0,
    )
    # billable_input = 1M - 500K = 500K → 500K * 2.50/M = 1.25
    # cached = 500K * 1.25/M = 0.625
    # output = 1M * 10.00/M = 10.00
    # total = 11.875
    assert r.cost_usd == Decimal("11.875000")
    assert r.estimated is False
