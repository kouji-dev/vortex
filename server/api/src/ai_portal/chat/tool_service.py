"""Chat domain — tool dispatch layer.

Handles execution of tool calls emitted by the LLM during streaming.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal

from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.tools import registry

log = logging.getLogger(__name__)


async def dispatch_tool(
    *,
    tool_name: str,
    call_id: str,
    arguments: dict,
    org_id: str,
    user_id: int | None = None,
) -> ToolCallOutcome:
    """Single entry point. Returns ToolCallOutcome; never raises."""
    t0 = time.monotonic()
    try:
        result = await registry.run_tool(
            tool_name=tool_name, arguments=arguments, org_id=org_id, user_id=user_id,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ToolCallOutcome(
            call_id=call_id,
            tool_name=tool_name,
            provider=result.get("provider") or "unknown",
            input=result.get("input") or arguments,
            result_snippet=result.get("result_snippet"),
            cost_usd=_as_decimal(result.get("cost_usd")),
            latency_ms=result.get("latency_ms") or latency_ms,
            chunks_meta=list(result.get("chunks_meta") or []),
        )
    except Exception as exc:
        log.exception("tool dispatch failed", extra={"tool_name": tool_name, "call_id": call_id})
        return ToolCallOutcome(
            call_id=call_id,
            tool_name=tool_name,
            provider="unknown",
            input=arguments,
            error=str(exc),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


def _as_decimal(v) -> Decimal | None:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))
