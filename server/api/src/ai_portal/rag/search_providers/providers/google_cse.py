"""Google Custom Search Engine provider."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ai_portal.rag.search_providers.protocol import SearchProviderResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_TIMEOUT = 15.0


class GoogleCseProvider:
    name = "google_cse"

    def __init__(
        self,
        api_key: str | None = None,
        cx: str | None = None,
        client: httpx.Client | None = None,
    ):
        self._api_key = (api_key or "").strip()
        self._cx = (cx or "").strip()
        self._client = client

    def search(
        self, query: str, *, num_results: int = 5, **_: Any
    ) -> list[SearchProviderResult]:
        if not self._api_key or not self._cx:
            log.warning("google_cse: missing api_key or cx")
            return []
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.get(
                _ENDPOINT,
                params={
                    "key": self._api_key,
                    "cx": self._cx,
                    "q": query,
                    "num": min(num_results, 10),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001
            log.exception("google_cse search failed: %r", query)
            return []
        items = data.get("items") or []
        return [
            SearchProviderResult(
                title=r.get("title", ""),
                url=r.get("link", ""),
                snippet=r.get("snippet", ""),
                source="google_cse",
            )
            for r in items
        ]
