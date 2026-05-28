"""BGE-reranker adapter — self-hosted HTTP endpoint.

Designed for BAAI's ``bge-reranker-*`` family served behind:

- HuggingFace text-embeddings-inference (TEI) ``/rerank``
- Infinity ``/rerank``
- Custom Triton / vllm wrapper

Wire shape we expect (TEI-compatible)::

    POST /rerank
    {"query": "...", "texts": ["..."], "raw_scores": false}

Response::

    [{"index": int, "score": float}, ...]
"""

from __future__ import annotations

import httpx

from ai_portal.gateway.rerank.protocol import RerankResult

BGE_DEFAULT_MODEL = "bge-reranker-large"


class BgeReranker:
    """Self-hosted BGE reranker (text-embeddings-inference / Infinity)."""

    name = "bge"

    def __init__(
        self,
        *,
        base_url: str,
        default_model: str = BGE_DEFAULT_MODEL,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._api_key = api_key
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
            "texts": documents,
            "model": model or self._default_model,
            "raw_scores": False,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/rerank", json=body, headers=headers
            )
        resp.raise_for_status()
        data = resp.json()
        out = [
            RerankResult(
                index=int(r["index"]),
                relevance_score=float(r["score"]),
                document=(
                    documents[int(r["index"])] if return_documents else None
                ),
            )
            for r in data
        ]
        out.sort(key=lambda r: r.relevance_score, reverse=True)
        if top_k is not None:
            out = out[:top_k]
        return out


__all__ = ["BgeReranker", "BGE_DEFAULT_MODEL"]
