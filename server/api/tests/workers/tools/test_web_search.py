"""Tests for the web_search tool — provider call + egress gating on endpoints."""

from __future__ import annotations

import pytest

from ai_portal.rag.search_providers.protocol import SearchProviderResult
from ai_portal.workers.egress.policy import EgressPolicy
from ai_portal.workers.tools.providers.web_search import WebSearchTool


class _FakeProvider:
    name = "fake-search"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query, *, num_results=5, **_):
        self.calls.append((query, num_results))
        return [
            SearchProviderResult(
                title="A", url="https://a.example/", snippet="hello", score=0.9
            ),
            SearchProviderResult(
                title="B", url="https://b.example/", snippet="world", score=0.5
            ),
        ]


@pytest.mark.asyncio
async def test_web_search_calls_configured_provider(harness) -> None:
    fake = _FakeProvider()
    _sb, _h, ctx, rec = await harness(
        pool_settings={"search_provider_instance": fake},
    )
    ctx.egress = EgressPolicy.from_list(["*.example", "a.example", "b.example"])
    r = await WebSearchTool().invoke({"query": "foo", "num_results": 5}, ctx)
    assert r.ok is True
    assert len(r.output["results"]) == 2
    assert r.output["results"][0]["title"] == "A"
    assert fake.calls == [("foo", 5)]
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
async def test_web_search_filters_results_by_egress(harness) -> None:
    fake = _FakeProvider()
    _sb, _h, ctx, _rec = await harness(
        pool_settings={"search_provider_instance": fake},
    )
    # Only allow b.example
    ctx.egress = EgressPolicy.from_list(["b.example"])
    r = await WebSearchTool().invoke({"query": "x"}, ctx)
    assert r.ok is True
    urls = [row["url"] for row in r.output["results"]]
    assert "https://a.example/" not in urls
    assert "https://b.example/" in urls


@pytest.mark.asyncio
async def test_web_search_no_provider_returns_error(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await WebSearchTool().invoke({"query": "x"}, ctx)
    assert r.ok is False
    assert "provider" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_web_search_audits_query(harness) -> None:
    fake = _FakeProvider()
    _sb, _h, ctx, rec = await harness(
        pool_settings={"search_provider_instance": fake},
    )
    ctx.egress = EgressPolicy.from_list(["*.example", "a.example", "b.example"])
    await WebSearchTool().invoke({"query": "secret query"}, ctx)
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.web_search"
    assert audit["payload"]["query"] == "secret query"
    assert audit["payload"]["result_count"] >= 1
