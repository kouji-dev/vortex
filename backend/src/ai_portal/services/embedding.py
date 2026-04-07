# Re-export shim — real implementation moved to rag/providers/voyage.py
from ai_portal.rag.providers.voyage import (  # noqa: F401
    embed_texts,
    embeddings_configured,
    embeddings_missing_key_message,
    VOYAGE_DEFAULT_EMBEDDING_MODEL,
)
