"""fetch_webpage tool — fetches a URL using Crawl4AI (stealth, JS rendering) with a
requests fallback. The provider chain is built once at module load time.
"""

from __future__ import annotations

import logging

from ai_portal.tools.fetch.factory import build_fetch_chain

logger = logging.getLogger(__name__)

_chain = build_fetch_chain()

SYSTEM_PROMPT = (
    "## Webpage Fetching\n"
    "Use the `fetch_webpage` tool to retrieve the full text of a specific URL. "
    "Typical use cases:\n"
    "- A `web_search` returned URLs with promising titles but thin snippets — fetch the best one.\n"
    "- The user asks you to read, summarize, or extract information from a specific link.\n"
    "- You need deeper detail (full article, stats page) that a snippet cannot provide.\n"
    "You can chain tools: call `web_search` first to find relevant URLs, then `fetch_webpage` "
    "on the most promising result. "
    "If a fetch fails or returns no useful content, try a different URL. "
    "Always synthesize what you fetched into a clear, direct answer for the user."
)


def system_prompt() -> str:
    return SYSTEM_PROMPT


def schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": (
                "Fetch and read the full text content of a webpage. "
                "Handles JavaScript-heavy sites and Cloudflare-protected pages. "
                "Use after web_search when you need more detail than the snippets provide."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the webpage to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    }


def execute(url: str) -> dict:
    content = _chain.fetch(url)
    return {"name": "fetch_webpage", "content": content, "_used_kbs": []}
