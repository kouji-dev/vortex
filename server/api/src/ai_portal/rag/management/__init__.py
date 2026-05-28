"""RAG management HTTP surface — evals, playground, analytics.

Mounted at ``/api/kbs/{id}/...`` to keep the URL surface consistent with
the rest of the RAG package.
"""
from ai_portal.rag.management.router import router

__all__ = ["router"]
