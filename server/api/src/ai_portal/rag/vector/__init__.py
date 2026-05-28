"""RAG vector store abstraction.

Public surface:

- :class:`VectorPoint`, :class:`VectorHit`, :class:`VectorFilter` — DTOs.
- :class:`VectorStore`                                            — Protocol.
- :func:`register`, :func:`get`, :func:`names`                    — registry.
- :func:`resolve_for_kb`                                          — per-KB.
- :exc:`UnknownVectorBackend`, :exc:`DuplicateBackend`            — errors.
"""

from __future__ import annotations

from ai_portal.rag.vector.protocol import (
    VectorFilter,
    VectorHit,
    VectorPoint,
    VectorStore,
)
from ai_portal.rag.vector.registry import (
    DuplicateBackend,
    UnknownVectorBackend,
    get,
    names,
    register,
)
from ai_portal.rag.vector.resolver import resolve_for_kb

__all__ = [
    "DuplicateBackend",
    "UnknownVectorBackend",
    "VectorFilter",
    "VectorHit",
    "VectorPoint",
    "VectorStore",
    "get",
    "names",
    "register",
    "resolve_for_kb",
]
