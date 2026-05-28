"""Exa (formerly Metaphor) neural search provider."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ai_portal.rag.search_providers.protocol import SearchProviderResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.exa.ai/search"
_TIMEOUT = 15.0


class ExaProvider:
    name = "exa"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self._api_key = (api_key or "").strip()
        self._client = client

    def search(
        self, query: str, *, num_results: int = 5, **_: Any
    ) -> list[SearchProviderResult]:
        if not self._api_key:
            log.warning("exa: no api key configured")
            return []
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            resp = client.post(
                _ENDPOINT,
                headers={"x-api-key": self._api_key},
                json={"query": query, "numResults": num_results, "useAutoprompt": True},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:  # noqa: BLE001
            log.exception("exa search failed: %r", query)
            return []
        return [
            SearchProviderResult(
                title=r.get("title", "") or "",
                url=r.get("url", ""),
                snippet=r.get("text", "") or r.get("highlight", "") or "",
                score=float(r.get("score") or 0.0),
                published_date=r.get("publishedDate"),
                source="exa",
            )
            for r in (data.get("results") or [])
        ]
