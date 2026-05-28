"""Rerank provider protocol — query + docs → ordered list of ``RerankResult``.

Cohere-shape on the wire; providers translate. Implementations live in
``rerank/providers/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RerankResult:
    """One doc's rerank score.

    ``index`` is the position in the *original* input list — Cohere-compatible
    so clients can map back without holding the docs themselves.
    """

    index: int
    relevance_score: float
    document: str | None = None  # echoed back when client requests it


@runtime_checkable
class Reranker(Protocol):
    """Score + reorder documents by relevance to a query.

    Implementations:
    - :class:`ai_portal.gateway.rerank.providers.voyage.VoyageReranker`
    - :class:`ai_portal.gateway.rerank.providers.cohere.CohereReranker`
    - :class:`ai_portal.gateway.rerank.providers.bge.BgeReranker` (self-hosted)
    """

    name: str

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int | None = None,
        model: str | None = None,
        return_documents: bool = False,
    ) -> list[RerankResult]:
        """Return docs sorted by descending relevance.

        ``top_k=None`` returns every doc. Otherwise truncates to top-k.
        """
        ...


__all__ = ["Reranker", "RerankResult"]
