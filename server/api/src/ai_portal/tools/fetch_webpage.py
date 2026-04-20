"""fetch_webpage tool — fetches a URL using Crawl4AI (stealth, JS rendering) with a
requests fallback. The provider chain is built once at module load time.
"""

from __future__ import annotations

import logging

from ai_portal.tools.fetch.factory import build_fetch_chain

logger = logging.getLogger(__name__)

_chain = build_fetch_chain()

SYSTEM_PROMPT = """\
## Fetch Webpage

Fetch when: user gives a specific URL, or search snippets are thin and a result URL looks useful.

- search -> thin snippets -> fetch the best result URL.
- Fetch fails or empty -> try next URL.
- Synthesise fetched content into a direct answer. Never dump raw text.
- NEVER fetch search engines (google.com, bing.com, duckduckgo.com, etc.) — use web_search for any search query.\
"""


def system_prompt() -> str:
    return SYSTEM_PROMPT


def schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": (
                "Fetch and read the full text content of a specific, known URL. "
                "Handles JavaScript-heavy sites and Cloudflare-protected pages. "
                "Use after web_search when you need more detail than the snippets provide. "
                "NEVER use this for search engines (google.com, bing.com, duckduckgo.com) — "
                "use web_search for any search query."
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


_SEARCH_ENGINE_HOSTS = {
    "google.com", "www.google.com",
    "bing.com", "www.bing.com",
    "duckduckgo.com", "www.duckduckgo.com",
    "yahoo.com", "search.yahoo.com",
    "baidu.com", "www.baidu.com",
    "yandex.com", "yandex.ru",
}


def _is_search_engine_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
        # Strip www. for comparison
        return host in _SEARCH_ENGINE_HOSTS or f"www.{host}" in _SEARCH_ENGINE_HOSTS
    except Exception:
        return False


def execute(url: str) -> dict:
    if _is_search_engine_url(url):
        logger.warning("fetch_webpage called with search engine URL=%r — redirecting to error", url)
        snippet = (
            f"Error: '{url}' is a search engine URL. "
            "Use the web_search tool to search the web instead of fetching a search engine directly."
        )
        return {
            "name": "fetch_webpage",
            "content": snippet,
            "result_snippet": snippet,
            "_used_kbs": [],
            "_provider": "blocked",
            "provider": "blocked",
        }
    content, provider = _chain.fetch(url)
    snippet = (content or "")[:500]
    return {
        "name": "fetch_webpage",
        "content": content,
        "result_snippet": snippet,
        "_used_kbs": [],
        "_provider": provider,
        "provider": provider,
    }
