"""Canonical types for RAG search."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SearchFilter:
    """Metadata filters applied at retrieval time.

    All filters are AND-combined. Empty fields are no-ops.
    """

    sources: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    date_from: datetime | None = None
    date_to: datetime | None = None

    def is_empty(self) -> bool:
        return not (
            self.sources
            or self.languages
            or self.authors
            or self.tags
            or self.date_from
            or self.date_to
        )


@dataclass
class SearchHit:
    """One retrieved chunk + scoring metadata."""

    chunk_id: str
    document_id: str
    kb_id: int
    text: str
    score: float
    meta: dict[str, Any] = field(default_factory=dict)
    # Optional rank components for debugging.
    lexical_rank: int | None = None
    dense_rank: int | None = None
    rerank_score: float | None = None


@dataclass
class SearchRequest:
    """Inputs for a hybrid search call."""

    query: str
    kb_ids: list[int]
    top_k: int = 10
    filter: SearchFilter = field(default_factory=SearchFilter)
    boost_freshness: bool = False
    boost_source_priority: dict[str, float] = field(default_factory=dict)
    rerank: bool = True
    actor_user_id: str | None = None
    actor_group_ids: tuple[str, ...] = ()
