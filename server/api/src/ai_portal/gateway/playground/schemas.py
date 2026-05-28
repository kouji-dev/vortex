"""Pydantic schemas for the playground HTTP surface.

Kept here so the router and service can share the shape without importing
each other's modules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SnapshotIn(BaseModel):
    """Free-form snapshot payload owned by the UI.

    Backend reads ``model`` + ``prompt`` + ``system`` + ``temperature`` +
    ``max_tokens`` + ``models`` to power the ``/run`` route; any extra keys
    survive in ``snapshot_json`` untouched so the UI can extend without
    bumping the API.
    """

    model: str | None = None
    models: list[str] | None = None
    prompt: str = ""
    system: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    name: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)


class SessionOut(BaseModel):
    id: str
    name: str
    snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RunRequest(BaseModel):
    """Direct-run payload — does not require persisting a session.

    ``models`` is the canonical multi-model field used by the UI; ``model``
    is a single-target convenience for callers that just want one.
    """

    prompt: str = ""
    system: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    model: str | None = None
    models: list[str] | None = None


class RunResult(BaseModel):
    """One row of a multi-model run."""

    model: str
    output: str = ""
    latency_ms: int = 0
    cost_cents: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None


class RunResponse(BaseModel):
    results: list[RunResult]


__all__ = [
    "RunRequest",
    "RunResponse",
    "RunResult",
    "SessionCreate",
    "SessionOut",
    "SnapshotIn",
]
