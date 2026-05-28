"""Pydantic schemas for the KB chat playground."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlaygroundSettings(BaseModel):
    top_k: int = 5
    min_score: float = 0.0
    rerank: bool = True
    model: str | None = None
    tone: str | None = None
    language: str | None = None


class PlaygroundRequest(BaseModel):
    """``POST /api/kbs/{id}/playground`` body."""

    query: str
    settings: PlaygroundSettings = Field(default_factory=PlaygroundSettings)
    save: bool = True


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    meta: dict[str, Any] = Field(default_factory=dict)


class PlaygroundResponse(BaseModel):
    session_id: _uuid.UUID | None = None
    query: str
    retrieved: list[RetrievedChunk]
    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)


class PlaygroundSessionOut(BaseModel):
    id: _uuid.UUID
    kb_id: int
    prompt: str
    settings: PlaygroundSettings
    retrieved: list[RetrievedChunk]
    answer: str | None
    created_at: datetime


__all__ = [
    "PlaygroundRequest",
    "PlaygroundResponse",
    "PlaygroundSessionOut",
    "PlaygroundSettings",
    "RetrievedChunk",
]
