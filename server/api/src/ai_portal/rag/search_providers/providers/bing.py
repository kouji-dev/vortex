"""Bing Web Search provider."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ai_portal.rag.search_providers.protocol import SearchProviderResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"
_TIMEOUT = 15.0


class BingProvider:
    name = "bing"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self._api_key = (api_key or "").strip()
        self._client = client

    def search(
        self, query: str, *, num_results: int = 5, **_: Any
    ) -> list[SearchProviderResult]:
        if not self._api_key:
            log.warning("bing: no api key configured")
            return []
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.get(
                _ENDPOINT,
                params={"q": query, "count": min(num_results, 50)},
                headers={"Ocp-Apim-Subscription-Key": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001
            log.exception("bing search failed: %r", query)
            return []
        web = (data.get("webPages") or {}).get("value") or []
        return [
            SearchProviderResult(
                title=r.get("name", ""),
                url=r.get("url", ""),
                snippet=r.get("snippet", ""),
                published_date=r.get("dateLastCrawled"),
                source="bing",
            )
            for r in web
        ]
