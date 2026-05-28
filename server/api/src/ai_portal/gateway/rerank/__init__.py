"""Rerank — query + documents → score-ordered list.

Public surface:

- :class:`Reranker` (Protocol) — provider contract
- :class:`RerankResult` — single scored doc
- Bundled providers (voyage, cohere, bge) live in :mod:`.providers`
"""

from ai_portal.gateway.rerank.protocol import (
    RerankResult,
    Reranker,
)

__all__ = ["Reranker", "RerankResult"]
