from __future__ import annotations

import logging

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds


class DuckDuckGoProvider(BaseSearchProvider):
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        try:
            with DDGS(timeout=_TIMEOUT) as ddgs:
                raw = ddgs.text(query, max_results=min(num_results, 10), region="wt-wt")
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                )
                for r in (raw or [])
            ]
        except Exception:
            logger.exception("duckduckgo_search_failed")
            return []
