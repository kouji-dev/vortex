"""Extractor protocol — pluggable memory extraction.

Implementers turn a list of conversation turns into a list of memory
``Candidate``s. The service layer is responsible for dedupe, sensitive
gating, and persistence; extractors stay pure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Turn:
    role: str
    content: str
    turn_id: str
    ts: float = 0.0


@dataclass
class ExtractScope:
    org_id: str
    actor_user_id: str
    scope_kind: str  # user|conversation|assistant|team|org
    scope_id: str
    conversation_id: str | None = None
    assistant_id: str | None = None


@dataclass
class ExtractOpts:
    model: str = "claude-sonnet-4-6"
    allowed_types: list[str] = field(
        default_factory=lambda: [
            "fact",
            "preference",
            "entity",
            "relation",
            "episode",
            "procedure",
        ]
    )
    block_sensitive_categories: list[str] = field(default_factory=list)
    confidence_floor: float = 0.4
    dedupe: bool = True
    max_candidates: int = 16


@dataclass
class Candidate:
    type: str
    text: str
    confidence: float
    source_turn_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@runtime_checkable
class Extractor(Protocol):
    name: str

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts,
    ) -> list[Candidate]: ...
