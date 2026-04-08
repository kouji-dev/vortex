"""Chat domain — tool dispatch layer.

Handles execution of tool calls emitted by the LLM during streaming.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

import ai_portal.tools.registry as tool_registry


def _dispatch_tool_call(
    db: Session,
    tool_call: dict,
    *,
    kb_ids: list[int],
) -> dict:
    """Execute a tool call emitted by the LLM. Returns tool result dict."""
    name = tool_call.get("name", "")
    try:
        args = json.loads(tool_call.get("arguments", "{}"))
    except Exception:
        args = {}
    return tool_registry.dispatch(name, args, db=db, kb_ids=kb_ids)
