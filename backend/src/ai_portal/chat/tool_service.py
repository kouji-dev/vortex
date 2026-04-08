"""Chat domain — tool dispatch layer.

Handles execution of tool calls emitted by the LLM during streaming.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ai_portal.rag import service as rag_svc
from ai_portal.tools.registry import ToolRegistry

_tool_registry = ToolRegistry()


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

    if name == "search_knowledge_base":
        query = args.get("query", "")
        requested_kb_ids = args.get("kb_ids") or kb_ids
        result = rag_svc.search_knowledge_base_tool(
            db=db, query=query, kb_ids=requested_kb_ids, top_k=args.get("top_k"),
        )
        return {
            "role": "tool",
            "name": name,
            "content": result["context"],
            "_used_kbs": result.get("used_kbs", []),
            "_citations": result.get("citations", []),
        }
    if name in ("web_search", "query_structured_data"):
        return _tool_registry.dispatch(name, args)
    return {"role": "tool", "name": name, "content": f"Error: unknown tool '{name}'"}
