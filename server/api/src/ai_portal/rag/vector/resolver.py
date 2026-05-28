"""Per-KB vector backend resolver."""

from __future__ import annotations

from ai_portal.rag.vector import registry
from ai_portal.rag.vector.protocol import VectorStore


def resolve_for_kb(kb, *, config: dict | None = None) -> VectorStore:
    """Resolve the vector backend selected by ``kb.vector_backend``.

    ``config`` is forwarded to the backend factory; unknown keys are
    ignored.

    Raises :exc:`UnknownVectorBackend` when the KB's selection is not
    registered.
    """
    backend_name = getattr(kb, "vector_backend", None) or "pgvector"
    return registry.get(backend_name, config or {})


def namespace_for_kb(kb) -> str:
    """Stable, opaque namespace token per KB.

    The token is fed to :meth:`VectorStore.ensure_namespace` and to all
    upsert/query/delete calls. Format: ``kb-<id>``.
    """
    kb_id = getattr(kb, "id", None)
    if kb_id is None:
        raise ValueError("kb has no id")
    return f"kb-{kb_id}"
