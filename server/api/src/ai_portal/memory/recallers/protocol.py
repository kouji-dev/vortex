"""Recaller protocol — pluggable memory retrieval."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class RecallScope:
    org_id: str
    actor_user_id: str
    team_ids: list[str] = field(default_factory=list)
    assistant_id: str | None = None
    conversation_id: str | None = None


@dataclass
class RecallFilters:
    types: list[str] | None = None
    scope_kinds: list[str] | None = None
    tags: list[str] | None = None
    time_from: float | None = None
    time_to: float | None = None
    source_assistant_id: str | None = None


@dataclass
class RecallOpts:
    top_k: int = 8
    recency_weight: float = 0.2
    importance_weight: float = 0.3
    bm25_weight: float = 0.0
    filters: RecallFilters | None = None


@dataclass
class Recalled:
    memory_id: str
    text: str
    score: float
    explain: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Recaller(Protocol):
    name: str

    async def recall(
        self,
        query: str,
        scope: RecallScope,
        opts: RecallOpts,
    ) -> list[Recalled]: ...
