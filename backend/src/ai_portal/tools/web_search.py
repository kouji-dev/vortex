"""web_search tool — always-on, hidden from the user.

Owns its schema, execution, and system prompt instruction.
"""

from __future__ import annotations

from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider

SYSTEM_PROMPT = (
    "You have access to the `web_search` tool. Use it when the question involves: "
    "recent events, current data, live prices or statistics, or facts you cannot reliably "
    "answer from training data alone. Do not use it for general knowledge you are confident about."
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


def execute(query: str, num_results: int = 5) -> dict:
    provider = DuckDuckGoProvider()
    results = provider.search(query, num_results=num_results)
    if not results:
        content = "Web search returned no results for this query."
    else:
        lines = [f"{i}. [{r.title}]({r.url})\n   {r.snippet}" for i, r in enumerate(results, 1)]
        content = "\n\n".join(lines)
    return {"name": "web_search", "content": content, "_used_kbs": []}
