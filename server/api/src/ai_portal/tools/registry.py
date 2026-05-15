"""Tool registry — central access point for tool definitions, prompts, and dispatch.

The streaming service calls only these three functions; it never imports
individual tool modules.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai_portal.catalog.providers.routing import (
    _is_gemini_model,
    is_langchain_anthropic_model,
)
from ai_portal.core.config import get_settings
from ai_portal.tools import fetch_webpage as fetch_webpage_tool
from ai_portal.tools import kb_search as kb_search_tool
from ai_portal.tools import web_search as web_search_tool

logger = logging.getLogger(__name__)


def _web_tools_enabled(capabilities: object | None) -> bool:
    """True when reflection or research capability is active."""
    if capabilities is None:
        return False
    return bool(getattr(capabilities, "reflection", False) or getattr(capabilities, "research", False))


def _native_anthropic_search_tool() -> dict:
    """Server-side web search tool for Anthropic models (executed by Anthropic, not us)."""
    settings = get_settings()
    return {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5,
        "user_location": {
            "type": "approximate",
            "country": settings.user_search_country,
            "timezone": "Europe/Paris",
        },
    }


def _native_gemini_search_tool() -> dict:
    """Google Search grounding tool for Gemini models (executed by Google, not us)."""
    return {
        "google_search_retrieval": {
            "dynamic_retrieval_config": {"mode": "MODE_DYNAMIC"}
        }
    }


def get_system_prompts(kb_ids: list[int], capabilities: object | None = None) -> list[str]:
    """Return tool system prompts for active tools only."""
    prompts = []
    if _web_tools_enabled(capabilities):
        prompts.append(fetch_webpage_tool.system_prompt())
        prompts.append(web_search_tool.system_prompt())
    if kb_ids:
        prompts.append(kb_search_tool.system_prompt())
    return prompts


def get_tool_definitions(
    kb_ids: list[int],
    model_id: str | None = None,
    capabilities: object | None = None,
) -> list[dict]:
    """Return tool schemas for the given model.

    Web search and fetch_webpage are only offered when reflection or research
    capability is active — prevents models like Gemini from calling web search
    on every message when the user hasn't asked for it.
    """
    tools: list[dict] = []

    if _web_tools_enabled(capabilities):
        if model_id and is_langchain_anthropic_model(model_id):
            # Anthropic's native server-side search (executed by Anthropic, no dispatch).
            tools.append(_native_anthropic_search_tool())
            tools.append(fetch_webpage_tool.schema())
        elif model_id and _is_gemini_model(model_id):
            # Gemini grounding marker — gemini_native.py reads tools with
            # ``type == "web_search"`` and switches to ``Tool(google_search=...)``,
            # which Google executes server-side (no tool-dispatch loop).
            tools.append({"type": "web_search", "name": "web_search"})
        else:
            # OpenAI / custom: our DuckDuckGo web_search function tool +
            # fetch_webpage for follow-up content extraction.
            tools.append(web_search_tool.schema())
            tools.append(fetch_webpage_tool.schema())

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
    """Route a tool call to the appropriate execute() function.

    Note: native provider tools (web_search_20260209, google_search_retrieval) are
    executed server-side and never reach this function.
    """
    if tool_name == "web_search":
        query = args.get("query", "")
        num_results = int(args.get("num_results", 5))
        region = args.get("region", "uk-en")
        return web_search_tool.execute(query, num_results, region)

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


async def run_tool(
    *,
    tool_name: str,
    arguments: dict,
    org_id: str,
    user_id: int | None = None,
) -> dict:
    """Async entry point used by tool_service.dispatch_tool.

    Runs the tool synchronously (all current tools are blocking I/O) and returns
    a normalised dict with at least: provider, result_snippet, input.
    Optional keys: cost_usd, latency_ms.

    Note: db and kb_ids are not available at this layer — callers that need
    knowledge-base search should use dispatch() directly via the streaming service.
    """
    import asyncio

    loop = asyncio.get_event_loop()

    if tool_name == "web_search":
        query = arguments.get("query", "")
        num_results = int(arguments.get("num_results", 5))
        region = arguments.get("region", "uk-en")
        raw = await loop.run_in_executor(
            None, lambda: web_search_tool.execute(query, num_results, region)
        )
        return {
            "provider": raw.get("_provider") or "unknown",
            "result_snippet": raw.get("result_snippet") or (raw.get("content") or "")[:500] or "",
            "input": arguments,
        }

    if tool_name == "fetch_webpage":
        url = arguments.get("url", "")
        raw = await loop.run_in_executor(None, lambda: fetch_webpage_tool.execute(url))
        return {
            "provider": raw.get("_provider") or "unknown",
            "result_snippet": raw.get("result_snippet") or (raw.get("content") or "")[:500] or "",
            "input": arguments,
        }

    if tool_name == "search_knowledge_base":
        # kb_search requires a DB session — not available at this layer; return error indicator
        return {
            "provider": "kb_search",
            "result_snippet": None,
            "input": arguments,
            "error": "search_knowledge_base requires a database session; use dispatch() instead",
        }

    logger.warning("run_tool: unknown tool_name=%s", tool_name)
    return {
        "provider": "unknown",
        "result_snippet": None,
        "input": arguments,
        "error": f"unknown tool '{tool_name}'",
    }
