"""Cohere rerank adapter — calls ``POST https://api.cohere.com/v1/rerank``.

Wire shape (Cohere v1)::

    POST /v1/rerank
    {"query": "...", "documents": ["..."], "model": "...", "top_n": N,
     "return_documents": false}

Response::

    {"results": [{"index": int, "relevance_score": float, ...}], ...}
"""

from __future__ import annotations

import httpx

from ai_portal.gateway.rerank.protocol import RerankResult

COHERE_DEFAULT_RERANK_MODEL = "rerank-english-v3.0"
COHERE_BASE_URL = "https://api.cohere.com"


class CohereReranker:
    """Cohere rerank via HTTPS."""

    name = "cohere"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = COHERE_BASE_URL,
        default_model: str = COHERE_DEFAULT_RERANK_MODEL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout_seconds

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

        body: dict = {
            "query": query,
            "documents": documents,
            "model": model or self._default_model,
            "return_documents": return_documents,
        }
        if top_k is not None:
            body["top_n"] = top_k

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/rerank",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        resp.raise_for_status()
        data = resp.json()
        out = [
            RerankResult(
                index=int(r["index"]),
                relevance_score=float(r["relevance_score"]),
                document=(
                    documents[int(r["index"])] if return_documents else None
                ),
            )
            for r in data.get("results", [])
        ]
        out.sort(key=lambda r: r.relevance_score, reverse=True)
        if top_k is not None:
            out = out[:top_k]
        return out


__all__ = ["CohereReranker", "COHERE_DEFAULT_RERANK_MODEL"]
