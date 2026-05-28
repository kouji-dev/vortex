"""Chunkers subpackage.

Each chunker turns an :class:`ExtractedDocument` into an async iterator
of :class:`Chunk`. The 8-stage ingest pipeline picks a chunker per KB
config via the :mod:`registry`.
"""
from __future__ import annotations

from ai_portal.rag.chunkers.protocol import (
    Chunk,
    Chunker,
    ChunkOpts,
    NoChunker,
)
from ai_portal.rag.chunkers.registry import (
    ChunkerRegistry,
    default_registry,
    register_builtins,
)

__all__ = [
    "Chunk",
    "ChunkOpts",
    "Chunker",
    "ChunkerRegistry",
    "NoChunker",
    "default_registry",
    "register_builtins",
]
