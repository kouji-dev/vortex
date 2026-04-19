"""Serper search provider (Google results via API).

Free tier: 2,500 one-time credits on signup, no credit card required.
Sign up: https://serper.dev
"""

from __future__ import annotations

import logging

import requests

from ai_portal.tools.search.base import BaseSearchProvider, SearchResult

logger = logging.getLogger(__name__)

_ENDPOINT = "https://google.serper.dev/search"
_TIMEOUT = 15


class SerperProvider(BaseSearchProvider):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        try:
            resp = requests.post(
                _ENDPOINT,
                headers={
                    "X-API-KEY": self._api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": min(num_results, 10)},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []

            # answerBox gives a direct answer — surface it as the first result
            answer_box = data.get("answerBox")
            if answer_box and answer_box.get("snippet"):
                results.append(SearchResult(
                    title=answer_box.get("title", "Answer"),
                    url=answer_box.get("link", ""),
                    snippet=answer_box["snippet"],
                ))

            for r in data.get("organic") or []:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("link", ""),
                    snippet=r.get("snippet", ""),
                    published_date=r.get("date"),
                ))
                if len(results) >= num_results:
                    break

            return results
        except Exception:
            logger.exception("serper_search_failed query=%r", query)
            return []
