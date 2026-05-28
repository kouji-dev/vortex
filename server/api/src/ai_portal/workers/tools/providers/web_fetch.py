"""Web fetch tool — outbound HTTP GET governed by pool egress policy.

The tool requires ``ctx.egress`` to be an :class:`EgressPolicy`. A missing
policy is a hard block (default-deny). When blocked, an
``egress_blocked`` event is emitted and the tool returns a failed
``ToolResult``. Audit captures the URL + sha256 of the body so leak
detection works without storing plaintext.
"""

from __future__ import annotations

import hashlib

import httpx

from ai_portal.workers.egress.policy import EgressPolicy, check_url
from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind

_DEFAULT_TIMEOUT = 20.0
_MAX_BODY_BYTES = 1_000_000


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class WebFetchTool:
    """HTTP GET a single URL, gated by the pool egress allow-list."""

    name = "web_fetch"
    schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "timeout_sec": {"type": "number", "default": _DEFAULT_TIMEOUT},
            "headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["url"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        url = args["url"]
        timeout = float(args.get("timeout_sec") or _DEFAULT_TIMEOUT)
        headers = dict(args.get("headers") or {})

        await ctx.emit_event(EventKind.tool_call, {"tool": "web_fetch", "url": url})

        policy = ctx.egress
        if not isinstance(policy, EgressPolicy):
            await ctx.emit_event(
                EventKind.egress_blocked,
                {"url": url, "reason": "no egress policy on context"},
            )
            return ToolResult(ok=False, error="egress blocked: no policy")

        decision = check_url(policy, url)
        if not decision.allowed:
            await ctx.emit_event(
                EventKind.egress_blocked,
                {"url": url, "host": decision.host, "reason": decision.reason},
            )
            if ctx.audit is not None:
                await ctx.audit(
                    {
                        "action": "worker.web_fetch.blocked",
                        "resource_type": "worker_run",
                        "resource_id": ctx.run_id,
                        "payload": {"url": url, "host": decision.host},
                    }
                )
            return ToolResult(
                ok=False, error=f"egress blocked: {decision.host}"
            )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                body_bytes = resp.content[:_MAX_BODY_BYTES]
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=f"http error: {e}")

        body_text = body_bytes.decode("utf-8", errors="replace")
        content_type = resp.headers.get("content-type", "")
        body_sha = _sha256(body_bytes)
        ok = 200 <= resp.status_code < 300

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.web_fetch",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "url": url,
                        "status": resp.status_code,
                        "body_sha256": body_sha,
                        "size": len(body_bytes),
                    },
                }
            )

        result_out = {
            "status": resp.status_code,
            "content_type": content_type,
            "body": body_text,
            "size": len(body_bytes),
            "body_sha256": body_sha,
        }
        return ToolResult(ok=ok, output=result_out)


_: Tool = WebFetchTool()  # protocol conformance check at import time
