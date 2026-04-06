from __future__ import annotations

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult


class TavilyProvider(BaseSearchProvider):
    """Stub — wire up when Tavily API key is available."""

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError("TavilyProvider is not yet configured.")
