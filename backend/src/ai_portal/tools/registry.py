"""Tool registry — central access point for tool definitions, prompts, and dispatch.

The streaming service calls only these three functions; it never imports
individual tool modules.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ai_portal.catalog.providers.routing import (
    is_langchain_anthropic_model,
    is_langchain_gemini_model,
)
from ai_portal.core.config import get_settings
from ai_portal.tools import fetch_webpage as fetch_webpage_tool
from ai_portal.tools import kb_search as kb_search_tool
from ai_portal.tools import web_search as web_search_tool

logger = logging.getLogger(__name__)


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


def get_system_prompts(kb_ids: list[int]) -> list[str]:
    """Always includes fetch_webpage prompt; adds web_search + kb_search when relevant."""
    prompts = [fetch_webpage_tool.system_prompt()]
    # Custom web_search system prompt only needed when our tool is active (non-native providers)
    prompts.append(web_search_tool.system_prompt())
    if kb_ids:
        prompts.append(kb_search_tool.system_prompt())
    return prompts


def get_tool_definitions(
    kb_ids: list[int],
    model_id: str | None = None,
) -> list[dict]:
    """Return tool schemas for the given model. Search tool varies by provider."""
    tools: list[dict] = []

    if model_id and is_langchain_anthropic_model(model_id):
        # Use Anthropic's native server-side search (no dispatch needed)
        tools.append(_native_anthropic_search_tool())
    elif model_id and is_langchain_gemini_model(model_id):
        # Use Google Search grounding (no dispatch needed)
        tools.append(_native_gemini_search_tool())
    else:
        # All other providers (OpenAI, custom): use our DuckDuckGo web_search tool
        tools.append(web_search_tool.schema())

    # fetch_webpage always uses our Crawl4AI chain
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
