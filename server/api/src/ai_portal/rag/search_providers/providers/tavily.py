"""Tavily web-search provider."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ai_portal.rag.search_providers.protocol import SearchProviderResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.tavily.com/search"
_TIMEOUT = 15.0


class TavilyProvider:
    name = "tavily"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self._api_key = (api_key or "").strip()
        self._client = client

    def search(
        self, query: str, *, num_results: int = 5, **_: Any
    ) -> list[SearchProviderResult]:
        if not self._api_key:
            log.warning("tavily: no api key configured")
            return []
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": min(num_results, 10),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001
            log.exception("tavily search failed: %r", query)
            return []
        return [
            SearchProviderResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                score=float(r.get("score") or 0.0),
                published_date=r.get("published_date"),
                source="tavily",
                meta={"raw_score": r.get("score")},
            )
            for r in (data.get("results") or [])
        ]
