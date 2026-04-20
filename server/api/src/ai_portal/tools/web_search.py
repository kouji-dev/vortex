"""web_search tool — always-on, hidden from the user.

Owns its schema, execution, and system prompt instruction.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal

from ai_portal.tools.search.factory import build_search_provider

# Providers with known zero cost; others rely on flat-rate pricing table
_ZERO_COST_PROVIDERS = {"duckduckgo"}


def _provider_cost(provider_name: str) -> dict:
    """Return cost_usd dict entry for known-free providers; omit for metered ones."""
    if provider_name in _ZERO_COST_PROVIDERS:
        return {"cost_usd": Decimal("0")}
    return {}

SYSTEM_PROMPT = """\
## Web Search

Search when: question involves current events, live data, recent releases, or anything \
you cannot answer confidently from training data.

Do NOT search when: the answer is clearly static knowledge, math, code, or the user is \
just chatting.

Query:
- Keywords only. Not full sentences.
- One focused intent per query.
- Bad results or no results -> rephrase once with different keywords.

Escalate:
- Snippets too thin to answer -> call `fetch_webpage` on the most relevant result URL.
- You already know the exact content URL (not a search engine) -> call `fetch_webpage` directly.
- NEVER pass search engine URLs (google.com, bing.com, etc.) to `fetch_webpage`.

After tools:
- Always write a complete answer. Never end your turn silently after a tool call.
- Cite your sources (URL or site name) inline.
- All fetches failed -> answer from training data, state it may be outdated.
- Never tell the user to visit a URL themselves — you fetch it.\
"""


def system_prompt() -> str:
    return SYSTEM_PROMPT


def schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. Use when the user asks about "
                "recent events, facts you are unsure about, or anything requiring up-to-date data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return. Default 5, max 10.",
                    },
                    "region": {
                        "type": "string",
                        "description": (
                            "Search region code. Default 'uk-en' (Europe/EUW). "
                            "Use 'us-en' for NA/US, 'wt-wt' for worldwide."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    }


_MIN_SNIPPET_CHARS = 200

# Unicode block ranges considered non-Latin (CJK, Japanese, Korean, Arabic, Hebrew, Thai…)
_NON_LATIN_RANGES = (
    (0x0600, 0x06FF),   # Arabic
    (0x0E00, 0x0E7F),   # Thai
    (0x0F00, 0x0FFF),   # Tibetan
    (0x1100, 0x11FF),   # Hangul Jamo
    (0x3000, 0x303F),   # CJK Symbols
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x3100, 0x312F),   # Bopomofo
    (0x3400, 0x4DBF),   # CJK Ext-A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xA000, 0xA48F),   # Yi Syllables
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0xF900, 0xFAFF),   # CJK Compatibility
    (0x20000, 0x2A6DF), # CJK Ext-B
)


def _non_latin_ratio(text: str) -> float:
    """Return the fraction of characters that fall in non-Latin Unicode ranges."""
    if not text:
        return 0.0
    count = sum(
        1 for ch in text
        if any(lo <= ord(ch) <= hi for lo, hi in _NON_LATIN_RANGES)
    )
    return count / len(text)


def _is_english_result(title: str, snippet: str, threshold: float = 0.15) -> bool:
    """Return True if the result appears to be in English (Latin script)."""
    combined = (title or "") + " " + (snippet or "")
    return _non_latin_ratio(combined) < threshold


def execute(query: str, num_results: int = 5, region: str = "uk-en") -> dict:
    from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider
    provider = build_search_provider()
    if isinstance(provider, DuckDuckGoProvider):
        results = provider.search(query, num_results=num_results, region=region)
    else:
        results = provider.search(query, num_results=num_results)

    if not results:
        snippet = "Web search returned no results for this query."
        return {
            "name": "web_search",
            "content": snippet,
            "result_snippet": snippet,
            "_used_kbs": [],
            "_top_urls": [],
            "_thin": True,
            "_provider": provider.name,
            "provider": provider.name,
            **_provider_cost(provider.name),
        }

    # Filter out non-English results using Unicode character analysis
    english_results = [r for r in results if _is_english_result(r.title, r.snippet)]

    if not english_results:
        snippet = "Web search returned only non-English results. No useful data found."
        return {
            "name": "web_search",
            "content": snippet,
            "result_snippet": snippet,
            "_used_kbs": [],
            "_top_urls": [],
            "_thin": True,
            "_provider": provider.name,
            "provider": provider.name,
            **_provider_cost(provider.name),
        }

    lines = [
        f"{i}. [{r.title}]({r.url})\n   {r.snippet}"
        for i, r in enumerate(english_results, 1)
    ]
    content = "\n\n".join(lines)
    top_urls = [r.url for r in english_results[:3] if r.url]
    total_snippet_len = sum(len(r.snippet or "") for r in english_results)
    thin = total_snippet_len < _MIN_SNIPPET_CHARS
    snippet = content[:500]

    return {
        "name": "web_search",
        "content": content,
        "result_snippet": snippet,
        "_used_kbs": [],
        "_top_urls": top_urls,
        "_thin": thin,
        "_provider": provider.name,
        "provider": provider.name,
        **_provider_cost(provider.name),
    }
