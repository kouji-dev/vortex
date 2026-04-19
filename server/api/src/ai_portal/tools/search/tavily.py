"""Tavily search provider.

Free tier: 1,000 credits/month, no credit card required.
Sign up: https://app.tavily.com
"""

from __future__ import annotations

import logging

import requests

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.tavily.com/search"
_TIMEOUT = 15


class TavilyProvider(BaseSearchProvider):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        try:
            resp = requests.post(
                _ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": min(num_results, 10),
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for r in data.get("results") or []:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    published_date=r.get("published_date"),
                ))
            return results
        except Exception:
            logger.exception("tavily_search_failed query=%r", query)
            return []
