"""Tool registry — central access point for tool definitions, prompts, and dispatch.

The streaming service calls only these three functions; it never imports
individual tool modules.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai_portal.tools import fetch_webpage as fetch_webpage_tool
from ai_portal.tools import kb_search as kb_search_tool
from ai_portal.tools import web_search as web_search_tool

logger = logging.getLogger(__name__)


def get_system_prompts(kb_ids: list[int]) -> list[str]:
    """Always includes web_search + fetch_webpage prompts; adds kb_search when KBs are present."""
    prompts = [web_search_tool.system_prompt(), fetch_webpage_tool.system_prompt()]
    if kb_ids:
        prompts.append(kb_search_tool.system_prompt())
    return prompts


def get_tool_definitions(kb_ids: list[int]) -> list[dict]:
    """Always includes web_search + fetch_webpage; adds kb_search when KBs are present."""
    tools = [web_search_tool.schema(), fetch_webpage_tool.schema()]
    if kb_ids:
        tools.append(kb_search_tool.schema(kb_ids))
    return tools


def dispatch(
    tool_name: str,
    args: dict,
    *,
    db: Session,
    kb_ids: list[int],
) -> dict:
    """Route a tool call to the appropriate execute() function."""
    if tool_name == "web_search":
        query = args.get("query", "")
        num_results = int(args.get("num_results", 5))
        return web_search_tool.execute(query, num_results)

    if tool_name == "fetch_webpage":
        url = args.get("url", "")
        return fetch_webpage_tool.execute(url)

    if tool_name == "search_knowledge_base":
        query = args.get("query", "")
        kb_ids_arg = args.get("kb_ids") or kb_ids or []
        top_k = args.get("top_k")
        return kb_search_tool.execute(query, kb_ids_arg, top_k, db)

    logger.warning("unknown_tool_call name=%s", tool_name)
    return {"name": tool_name, "content": f"Error: unknown tool '{tool_name}'", "_used_kbs": []}
