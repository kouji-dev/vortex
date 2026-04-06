from __future__ import annotations

import logging

from ai_portal.tools.data.query import query_structured_data
from ai_portal.tools.search.duckduckgo import DuckDuckGoProvider

logger = logging.getLogger(__name__)


class ToolRegistry:
    def dispatch(self, name: str, args: dict) -> dict:
        if name == "web_search":
            return self._web_search(args)
        if name == "query_structured_data":
            return self._query_structured_data(args)
        return {"role": "tool", "name": name, "content": f"Error: unknown tool '{name}'"}

    def _web_search(self, args: dict) -> dict:
        query = args.get("query", "")
        num_results = int(args.get("num_results", 5))
        provider = DuckDuckGoProvider()
        results = provider.search(query, num_results=num_results)
        if not results:
            content = "Web search returned no results for this query."
        else:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r.title}]({r.url})\n   {r.snippet}")
            content = "\n\n".join(lines)
        return {"role": "tool", "name": "web_search", "content": content}

    def _query_structured_data(self, args: dict) -> dict:
        data = args.get("data", "")
        question = args.get("question", "")
        content = query_structured_data(data, question)
        return {"role": "tool", "name": "query_structured_data", "content": content}
