"""Browser tool — Playwright driver in the worker sandbox.

Playwright is heavy; we lazy-import the real driver and accept a
``browser_driver`` override in ``ctx.pool_settings`` for tests + custom
implementations.

Driver interface (duck-typed):
    async navigate(url) -> None
    async click(selector) -> None
    async get_text() -> str
    async screenshot() -> bytes
    async close() -> None

Screenshots are emitted as ``tool_result`` events so the live UI can
stream them; the base64 payload is also returned for the agent.
"""

from __future__ import annotations

import base64
import hashlib

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _load_playwright_driver():
    """Lazy import — raises ImportError if Playwright is not available."""
    raise ImportError(
        "playwright driver not available; install playwright and provide a "
        "sandbox-bound driver in pool_settings['browser_driver']"
    )


def _resolve_driver(ctx: ToolContext):
    settings = ctx.pool_settings or {}
    drv = settings.get("browser_driver")
    if drv is not None:
        return drv
    # Lazy import path — never executed in tests with a stub driver.
    return _load_playwright_driver()


class BrowserTool:
    """Drive a Playwright browser inside the sandbox."""

    name = "browser"
    schema = {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["navigate", "click", "get_text", "screenshot"],
            },
            "url": {"type": "string"},
            "selector": {"type": "string"},
        },
        "required": ["op"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        op = args.get("op")
        await ctx.emit_event(
            EventKind.tool_call, {"tool": "browser", "op": op}
        )

        if op not in {"navigate", "click", "get_text", "screenshot"}:
            return ToolResult(ok=False, error=f"unknown op: {op}")

        try:
            drv = _resolve_driver(ctx)
        except ImportError as e:
            return ToolResult(ok=False, error=str(e))
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"driver init failed: {e}")

        try:
            if op == "navigate":
                url = args.get("url")
                if not url:
                    return ToolResult(ok=False, error="navigate requires url")
                await drv.navigate(url)
                return ToolResult(ok=True, output={"op": "navigate", "url": url})

            if op == "click":
                sel = args.get("selector")
                if not sel:
                    return ToolResult(ok=False, error="click requires selector")
                await drv.click(sel)
                return ToolResult(ok=True, output={"op": "click", "selector": sel})

            if op == "get_text":
                text = await drv.get_text()
                return ToolResult(
                    ok=True, output={"op": "get_text", "text": text}
                )

            # screenshot
            png = await drv.screenshot()
            b64 = base64.b64encode(png).decode("ascii")
            sha = hashlib.sha256(png).hexdigest()
            # Stream the screenshot to subscribers for live view.
            await ctx.emit_event(
                EventKind.tool_result,
                {
                    "tool": "browser",
                    "op": "screenshot",
                    "screenshot_b64": b64,
                    "size": len(png),
                    "sha256": sha,
                },
            )
            return ToolResult(
                ok=True,
                output={
                    "op": "screenshot",
                    "screenshot_b64": b64,
                    "size": len(png),
                    "sha256": sha,
                },
                artifacts=[
                    {
                        "kind": "screenshot",
                        "sha256": sha,
                        "size": len(png),
                        "encoding": "base64",
                    }
                ],
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"browser op failed: {e}")


_: Tool = BrowserTool()
