"""RAG search subpackage — hybrid (BM25+dense) retrieval, RRF fusion,
filters/boosts, rerank, federated multi-KB search."""

from ai_portal.rag.search.rrf import reciprocal_rank_fusion
from ai_portal.rag.search.types import SearchFilter, SearchHit, SearchRequest

__all__ = ["reciprocal_rank_fusion", "SearchFilter", "SearchHit", "SearchRequest"]
