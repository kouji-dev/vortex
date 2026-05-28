"""Memory recaller protocol, registry, and bundled implementations.

Bundled recallers register themselves on import.
"""
from __future__ import annotations

from .protocol import RecallFilters, RecallOpts, RecallScope, Recalled, Recaller
from .registry import get, list_names, register

from . import vector_pgvector  # noqa: F401
from . import vector_qdrant  # noqa: F401
from . import hybrid  # noqa: F401

__all__ = [
    "RecallFilters",
    "RecallOpts",
    "RecallScope",
    "Recalled",
    "Recaller",
    "get",
    "list_names",
    "register",
]
