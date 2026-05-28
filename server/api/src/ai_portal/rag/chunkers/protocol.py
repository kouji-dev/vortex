"""Chunker protocol + token counter helpers."""
from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ai_portal.rag.extractors.protocol import ExtractedDocument


@dataclass(slots=True)
class ChunkOpts:
    """Per-call chunker configuration. Defaults match the spec."""

    max_tokens: int = 512
    overlap_tokens: int = 64
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    """One emitted chunk."""

    text: str
    index: int
    token_count: int
    meta: dict[str, Any] = field(default_factory=dict)


class NoChunker(LookupError):
    """Raised when the registry cannot resolve a chunker by id."""


@runtime_checkable
class Chunker(Protocol):
    """Async-iterator chunker contract."""

    name: str

    def chunk(
        self, doc: ExtractedDocument, opts: ChunkOpts
    ) -> AsyncIterator[Chunk]:  # pragma: no cover - protocol
        ...


# ── token counting ───────────────────────────────────────────────────────

_WORD_RE = re.compile(r"\S+")


def count_tokens(text: str) -> int:
    """Best-effort token count.

    Prefers :mod:`tiktoken` when installed. Falls back to whitespace word
    count when not — the resulting estimate is close enough for chunk
    budgeting in tests and small docs.
    """
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(_WORD_RE.findall(text))


__all__ = [
    "Chunk",
    "ChunkOpts",
    "Chunker",
    "NoChunker",
    "count_tokens",
]
