"""Brave Search provider."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ai_portal.rag.search_providers.protocol import SearchProviderResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT = 15.0


class BraveProvider:
    name = "brave"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self._api_key = (api_key or "").strip()
        self._client = client

    def search(
        self, query: str, *, num_results: int = 5, **_: Any
    ) -> list[SearchProviderResult]:
        if not self._api_key:
            log.warning("brave: no api key configured")
            return []
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.get(
                _ENDPOINT,
                params={"q": query, "count": min(num_results, 20)},
                headers={
                    "X-Subscription-Token": self._api_key,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001
            log.exception("brave search failed: %r", query)
            return []
        web = (data.get("web") or {}).get("results") or []
        return [
            SearchProviderResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", "") or "",
                published_date=r.get("page_age"),
                source="brave",
            )
            for r in web
        ]
