"""Tests for the browser tool — Playwright with a fake driver."""

from __future__ import annotations

import base64

import pytest

from ai_portal.workers.tools.providers.browser import BrowserTool


class _FakeDriver:
    """Stub stand-in for the Playwright async page driver."""

    def __init__(self) -> None:
        self.actions: list[dict] = []
        self._page_text = "Hello world"
        self._screenshot_bytes = b"\x89PNG\r\n\x1a\nfakepng"

    async def navigate(self, url: str) -> None:
        self.actions.append({"op": "navigate", "url": url})

    async def click(self, selector: str) -> None:
        self.actions.append({"op": "click", "selector": selector})

    async def get_text(self) -> str:
        self.actions.append({"op": "get_text"})
        return self._page_text

    async def screenshot(self) -> bytes:
        self.actions.append({"op": "screenshot"})
        return self._screenshot_bytes

    async def close(self) -> None:
        self.actions.append({"op": "close"})


@pytest.mark.asyncio
async def test_browser_navigate_then_text(harness) -> None:
    drv = _FakeDriver()
    _sb, _h, ctx, rec = await harness(
        pool_settings={"browser_driver": drv},
    )
    r = await BrowserTool().invoke(
        {"op": "navigate", "url": "https://example.com"}, ctx
    )
    assert r.ok is True
    assert drv.actions[0] == {"op": "navigate", "url": "https://example.com"}

    r2 = await BrowserTool().invoke({"op": "get_text"}, ctx)
    assert r2.ok is True
    assert r2.output["text"] == "Hello world"
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
async def test_browser_click(harness) -> None:
    drv = _FakeDriver()
    _sb, _h, ctx, _rec = await harness(pool_settings={"browser_driver": drv})
    r = await BrowserTool().invoke(
        {"op": "click", "selector": "button#submit"}, ctx
    )
    assert r.ok is True
    assert drv.actions[-1] == {"op": "click", "selector": "button#submit"}


@pytest.mark.asyncio
async def test_browser_screenshot_streams_event_and_returns_b64(harness) -> None:
    drv = _FakeDriver()
    _sb, _h, ctx, rec = await harness(pool_settings={"browser_driver": drv})
    r = await BrowserTool().invoke({"op": "screenshot"}, ctx)
    assert r.ok is True
    # Result includes base64 payload
    assert r.output["screenshot_b64"]
    assert base64.b64decode(r.output["screenshot_b64"]) == drv._screenshot_bytes
    # An artifact entry is emitted for the screenshot.
    assert r.artifacts
    assert r.artifacts[0]["kind"] == "screenshot"
    # A streaming event is emitted so UI can display live.
    payloads = [p for _, p in rec.events]
    assert any("screenshot_b64" in p for p in payloads)


@pytest.mark.asyncio
async def test_browser_no_driver_returns_error(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await BrowserTool().invoke({"op": "navigate", "url": "x"}, ctx)
    assert r.ok is False
    assert "playwright" in (r.error or "").lower() or "driver" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_browser_unknown_op_errors(harness) -> None:
    drv = _FakeDriver()
    _sb, _h, ctx, _rec = await harness(pool_settings={"browser_driver": drv})
    r = await BrowserTool().invoke({"op": "teleport"}, ctx)
    assert r.ok is False
    assert "unknown" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_browser_lazy_import_failure_is_clean(harness, monkeypatch) -> None:
    """When no driver is configured AND the lazy import fails, we still get a
    clean ToolResult, not an ImportError."""
    from ai_portal.workers.tools.providers import browser as browser_mod

    def _raise():
        raise ImportError("playwright not installed")

    monkeypatch.setattr(browser_mod, "_load_playwright_driver", _raise, raising=True)
    _sb, _h, ctx, _rec = await harness()
    r = await BrowserTool().invoke({"op": "navigate", "url": "https://x"}, ctx)
    assert r.ok is False
    assert "playwright" in (r.error or "").lower()
