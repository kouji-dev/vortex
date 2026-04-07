# Re-export shim — real implementation moved to rag/service.py
from ai_portal.rag.service import (  # noqa: F401
    retrieve_context_with_meta,
    search_knowledge_base_tool,
    _rrf_merge,
    _rerank_chunks,
    _cosine_score,
)
