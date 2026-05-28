"""Pydantic schemas for the pluggable memory subsystem."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScopeKindLiteral = Literal["user", "conversation", "assistant", "team", "org"]
MemoryTypeLiteral = Literal[
    "fact", "preference", "entity", "relation", "episode", "procedure"
]


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: _uuid.UUID
    org_id: _uuid.UUID
    type: MemoryTypeLiteral
    scope_kind: ScopeKindLiteral
    scope_ids: list[str] = Field(default_factory=list, alias="scope_ids_json")
    text: str
    importance: float
    confidence: float
    pinned: bool
    tags: list[str] = Field(default_factory=list, alias="tags_json")
    source_conversation_id: int | None = None
    source_turn_ids: list[str] = Field(default_factory=list, alias="source_turn_ids_json")
    extractor_model: str
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    deleted_at: datetime | None = None


class MemoryCreate(BaseModel):
    type: MemoryTypeLiteral
    scope_kind: ScopeKindLiteral
    scope_ids: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1, max_length=4096)
    importance: float = 0.5
    confidence: float = 0.9
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v


class MemoryPatch(BaseModel):
    text: str | None = Field(default=None, max_length=4096)
    pinned: bool | None = None
    importance: float | None = None
    tags: list[str] | None = None
    confidence: float | None = None


class BulkDeleteRequest(BaseModel):
    ids: list[_uuid.UUID] | None = None
    type: MemoryTypeLiteral | None = None
    scope_kind: ScopeKindLiteral | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None


class RecallFiltersDTO(BaseModel):
    types: list[MemoryTypeLiteral] | None = None
    scope_kinds: list[ScopeKindLiteral] | None = None
    tags: list[str] | None = None
    time_from: float | None = None
    time_to: float | None = None
    source_assistant_id: str | None = None


class RecallRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = 8
    recency_weight: float = 0.2
    importance_weight: float = 0.3
    filters: RecallFiltersDTO | None = None
    scope_kind: ScopeKindLiteral | None = None
    scope_id: str | None = None
    conversation_id: int | None = None
    assistant_id: str | None = None


class RecallResult(BaseModel):
    memory_id: _uuid.UUID
    text: str
    score: float
    explain: dict[str, Any] = Field(default_factory=dict)


class ExtractTurnDTO(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    turn_id: str
    ts: float = 0.0


class ExtractRequest(BaseModel):
    turns: list[ExtractTurnDTO]
    scope_kind: ScopeKindLiteral
    scope_id: str
    conversation_id: int | None = None
    assistant_id: str | None = None
    model: str = "claude-sonnet-4-6"
    extractor: str = "llm_default"
    block_sensitive_categories: list[str] = Field(default_factory=list)
    allowed_types: list[MemoryTypeLiteral] = Field(
        default_factory=lambda: list(
            ("fact", "preference", "entity", "relation", "episode", "procedure")
        )
    )
    confidence_floor: float = 0.4


class ExtractionPolicyDTO(BaseModel):
    scope_kind: ScopeKindLiteral
    triggers: dict[str, bool] = Field(default_factory=dict)
    sensitive_block: list[str] = Field(default_factory=list)
    model_allow: list[str] = Field(default_factory=list)
    conflict_strategy: Literal["newer_wins", "keep_both", "prompt_user"] = "newer_wins"
    retention_days: dict[str, int] = Field(default_factory=dict)


class RecallPolicyDTO(BaseModel):
    scope_kind: ScopeKindLiteral
    top_k: int = 8
    recency_weight: float = 0.2
    importance_weight: float = 0.3
    filters: dict[str, Any] = Field(default_factory=dict)


class PauseRequest(BaseModel):
    scope_kind: ScopeKindLiteral | None = None
    scope_id: str | None = None


class BulkPinRequest(BaseModel):
    ids: list[_uuid.UUID] = Field(min_length=1)
    pinned: bool


class BulkTagRequest(BaseModel):
    ids: list[_uuid.UUID] = Field(min_length=1)
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
