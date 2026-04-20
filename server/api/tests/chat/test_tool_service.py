from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.chat.tool_service import dispatch_tool


@pytest.mark.asyncio
async def test_dispatch_returns_tool_call_outcome(monkeypatch):
    fake_run = AsyncMock(return_value={
        "provider": "tavily",
        "result_snippet": "found",
        "input": {"q": "hi"},
    })
    monkeypatch.setattr("ai_portal.tools.registry.run_tool", fake_run)

    outcome = await dispatch_tool(
        tool_name="web_search", call_id="c1", arguments={"q": "hi"}, org_id="org-1",
    )
    assert isinstance(outcome, ToolCallOutcome)
    assert outcome.provider == "tavily"
    assert outcome.result_snippet == "found"


@pytest.mark.asyncio
async def test_dispatch_captures_errors_into_outcome(monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("rate limited")
    monkeypatch.setattr("ai_portal.tools.registry.run_tool", boom)

    outcome = await dispatch_tool(
        tool_name="web_search", call_id="c1", arguments={"q": "hi"}, org_id="org-1",
    )
    assert outcome.error == "rate limited"
    assert outcome.result_snippet is None


@pytest.mark.asyncio
async def test_dispatch_propagates_metered_cost(monkeypatch):
    async def metered(*a, **kw):
        return {
            "provider": "firecrawl",
            "result_snippet": "ok",
            "input": {"url": "x"},
            "cost_usd": Decimal("0.042"),
            "latency_ms": 140,
        }
    monkeypatch.setattr("ai_portal.tools.registry.run_tool", metered)

    outcome = await dispatch_tool(
        tool_name="scrape", call_id="c1", arguments={"url": "x"}, org_id="org-1",
    )
    assert outcome.cost_usd == Decimal("0.042")
    assert outcome.latency_ms == 140
