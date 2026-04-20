from decimal import Decimal
import pytest
from pydantic import ValidationError
from ai_portal.chat.tool_outcome import ToolCallOutcome


def test_outcome_minimum_shape():
    o = ToolCallOutcome(
        call_id="c1", tool_name="web_search", provider="tavily",
        input={"q": "x"}, result_snippet="ok",
    )
    assert o.cost_usd is None
    assert o.error is None


def test_outcome_with_metered_cost():
    o = ToolCallOutcome(
        call_id="c1", tool_name="scrape", provider="firecrawl",
        input={"url": "x"}, result_snippet="ok",
        cost_usd=Decimal("0.0042"), latency_ms=120,
    )
    assert o.cost_usd == Decimal("0.0042")
    assert o.latency_ms == 120


def test_outcome_error_case():
    o = ToolCallOutcome(
        call_id="c1", tool_name="web_search", provider="tavily",
        input={}, error="rate limited",
    )
    assert o.error == "rate limited"
    assert o.result_snippet is None


def test_outcome_requires_result_or_error():
    with pytest.raises(ValidationError):
        ToolCallOutcome(call_id="c1", tool_name="web_search", provider="tavily", input={})
