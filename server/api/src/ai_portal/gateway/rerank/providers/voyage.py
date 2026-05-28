"""Voyage rerank adapter.

Wraps the ``voyageai.Client.rerank`` call. The sync SDK is invoked in a
threadpool so :meth:`VoyageReranker.rerank` can stay ``async`` and play nice
with the rest of the gateway.

Reuses ``VOYAGE_API_KEY`` from settings (same key the RAG module's
``voyage.py`` embedder reads).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from ai_portal.gateway.rerank.protocol import RerankResult

VOYAGE_DEFAULT_RERANK_MODEL = "rerank-2"


class VoyageReranker:
    """Voyage rerank via the official ``voyageai`` SDK."""

    name = "voyage"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str = VOYAGE_DEFAULT_RERANK_MODEL,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._client_factory = client_factory

    def _client(self):  # pragma: no cover — exercised by integration
        if self._client_factory is not None:
            return self._client_factory(self._api_key)
        from voyageai import Client  # pylint: disable=import-error

        return Client(api_key=self._api_key)

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int | None = None,
        model: str | None = None,
        return_documents: bool = False,
    ) -> list[RerankResult]:
        if not documents:
            return []
        client = self._client()
        mdl = model or self._default_model

        def _call():
            kwargs: dict[str, Any] = {
                "query": query,
                "documents": documents,
                "model": mdl,
            }
            if top_k is not None:
                kwargs["top_k"] = top_k
            return client.rerank(**kwargs)

        raw = await asyncio.to_thread(_call)
        results = list(getattr(raw, "results", []) or [])
        out = [
            RerankResult(
                index=int(r.index),
                relevance_score=float(r.relevance_score),
                document=documents[int(r.index)] if return_documents else None,
            )
            for r in results
        ]
        out.sort(key=lambda r: r.relevance_score, reverse=True)
        if top_k is not None:
            out = out[:top_k]
        return out


__all__ = ["VoyageReranker", "VOYAGE_DEFAULT_RERANK_MODEL"]
