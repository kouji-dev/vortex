"""Exa (formerly Metaphor) neural search provider.

Free tier: 1,000 searches/month, no credit card required.
Sign up: https://exa.ai
"""

from __future__ import annotations

import logging

import requests

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.exa.ai/search"
_TIMEOUT = 15
_SNIPPET_MAX_CHARS = 500


class ExaProvider(BaseSearchProvider):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        try:
            resp = requests.post(
                _ENDPOINT,
                headers={
                    "x-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "numResults": min(num_results, 10),
                    "type": "auto",           # auto = neural or keyword based on query
                    "contents": {
                        "text": {"maxCharacters": _SNIPPET_MAX_CHARS},
                    },
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
                    snippet=r.get("text", ""),
                    published_date=r.get("publishedDate"),
                ))
            return results
        except Exception:
            logger.exception("exa_search_failed query=%r", query)
            return []
