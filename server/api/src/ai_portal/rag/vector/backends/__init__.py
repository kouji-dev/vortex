"""Bundled vector backends.

Importing this package registers the default backends under their canonical
names. Production code should call :func:`ensure_registered` exactly once at
startup; tests may inline-import a backend module to register only what they
need.
"""

from __future__ import annotations


def ensure_registered() -> None:
    """Register all bundled backends (idempotent)."""
    from ai_portal.rag.vector import registry
    from ai_portal.rag.vector.backends import (
        memory,
        pgvector,
        pinecone,
        qdrant,
        weaviate,
    )

    for module, name in (
        (memory, "memory"),
        (pgvector, "pgvector"),
        (qdrant, "qdrant"),
        (pinecone, "pinecone"),
        (weaviate, "weaviate"),
    ):
        try:
            registry.register(name, module.build)
        except registry.DuplicateBackend:
            continue


__all__ = ["ensure_registered"]
