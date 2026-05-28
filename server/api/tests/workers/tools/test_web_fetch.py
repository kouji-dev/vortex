"""Tests for the web_fetch tool — egress gating, audit, content shape."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.egress.policy import EgressBlocked, EgressPolicy
from ai_portal.workers.tools.providers.web_fetch import WebFetchTool


@pytest.mark.asyncio
async def test_web_fetch_blocked_when_host_not_allowed(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    ctx.egress = EgressPolicy.from_list(["api.allowed.com"])
    t = WebFetchTool()
    r = await t.invoke({"url": "https://evil.example/x"}, ctx)
    assert r.ok is False
    assert "egress" in (r.error or "").lower()
    # Event emitted for blocked egress.
    kinds = [k for k, _ in rec.events]
    assert "egress_blocked" in kinds


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_returns_body_when_allowed(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    ctx.egress = EgressPolicy.from_list(["example.com"])
    respx.get("https://example.com/page").mock(
        return_value=httpx.Response(200, text="hello world", headers={"content-type": "text/html"})
    )
    r = await WebFetchTool().invoke({"url": "https://example.com/page"}, ctx)
    assert r.ok is True
    assert r.output["status"] == 200
    assert r.output["body"] == "hello world"
    assert r.output["content_type"].startswith("text/html")
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_audits_url_and_hash(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    ctx.egress = EgressPolicy.from_list(["example.com"])
    respx.get("https://example.com/x").mock(
        return_value=httpx.Response(200, text="abc")
    )
    await WebFetchTool().invoke({"url": "https://example.com/x"}, ctx)
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.web_fetch"
    assert audit["payload"]["url"] == "https://example.com/x"
    assert "body_sha256" in audit["payload"]


@pytest.mark.asyncio
async def test_web_fetch_no_egress_policy_blocks_by_default(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    ctx.egress = None
    r = await WebFetchTool().invoke({"url": "https://example.com/x"}, ctx)
    assert r.ok is False
    assert "egress" in (r.error or "").lower()


@pytest.mark.asyncio
@respx.mock
async def test_web_fetch_non_2xx_marked_failure(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    ctx.egress = EgressPolicy.from_list(["example.com"])
    respx.get("https://example.com/missing").mock(
        return_value=httpx.Response(404, text="nope")
    )
    r = await WebFetchTool().invoke({"url": "https://example.com/missing"}, ctx)
    assert r.ok is False
    assert r.output["status"] == 404
