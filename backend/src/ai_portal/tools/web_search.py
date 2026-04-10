"""web_search tool — always-on, hidden from the user.

Owns its schema, execution, and system prompt instruction.
"""

from __future__ import annotations

from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider

SYSTEM_PROMPT = (
    "## Web Search\n"
    "Use the `web_search` tool for: current events, live data (prices, rankings, scores), "
    "recent releases, or any fact you cannot confidently answer from training data.\n"
    "Strategy:\n"
    "- Write a focused, specific query — avoid vague or overly broad terms.\n"
    "- If the first search returns no results, rephrase and try once more with a different query.\n"
    "- If snippets are too thin to answer the question, call `fetch_webpage` on the most "
    "relevant URL from the results.\n"
    "- If search returns no results and you know a reliable URL for this data "
    "(e.g. op.gg for LoL rankings, a stats site, an official leaderboard page), "
    "you MUST call `fetch_webpage` on that URL directly. "
    "NEVER just tell the user to visit a website — always fetch it yourself first.\n"
    "- After all tool calls, ALWAYS write a complete response. Never end your turn silently."
)


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
                },
                "required": ["query"],
            },
        },
    }


_MIN_SNIPPET_CHARS = 200  # below this total, snippets are considered too thin to answer from


def execute(query: str, num_results: int = 5) -> dict:
    provider = DuckDuckGoProvider()
    results = provider.search(query, num_results=num_results)
    if not results:
        content = "Web search returned no results for this query."
        top_urls: list[str] = []
        thin = True
    else:
        lines = [f"{i}. [{r.title}]({r.url})\n   {r.snippet}" for i, r in enumerate(results, 1)]
        content = "\n\n".join(lines)
        top_urls = [r.url for r in results[:3] if r.url]
        total_snippet_len = sum(len(r.snippet or "") for r in results)
        thin = total_snippet_len < _MIN_SNIPPET_CHARS
    return {"name": "web_search", "content": content, "_used_kbs": [], "_top_urls": top_urls, "_thin": thin}
