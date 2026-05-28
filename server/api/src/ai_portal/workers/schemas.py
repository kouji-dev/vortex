"""Pydantic schemas for the workers HTTP API."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── task submit ─────────────────────────────────────────────────


class SubmitTaskBody(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=8192)
    repo: str = Field(min_length=1, max_length=255)
    base_branch: str = Field(default="main", max_length=128)
    pool_id: str | None = None
    trigger_source: str = Field(default="rest_api", max_length=32)
    extra: dict[str, Any] = Field(default_factory=dict)


class TaskOut(BaseModel):
    id: str
    org_id: str
    pool_id: str | None
    title: str
    description: str
    repo: str | None
    base_branch: str
    status: str
    trigger_source: str
    created_by: str | None
    created_at: datetime
    completed_at: datetime | None


class RunOut(BaseModel):
    id: str
    task_id: str
    attempt_no: int
    status: str
    started_at: datetime
    ended_at: datetime | None
    cost_cents: int
    error: str | None


# ── control ─────────────────────────────────────────────────────


class UserMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=8192)


class CancelReasonBody(BaseModel):
    reason: str | None = Field(default=None, max_length=2048)


class ApprovalDecideBody(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str | None = Field(default=None, max_length=2048)


# ── pool ────────────────────────────────────────────────────────


class PoolIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    template: str = Field(default="python", max_length=64)
    sandbox_provider: str = Field(default="docker", max_length=32)
    repo_allow_list: list[str] = Field(default_factory=list)
    budget_cents_per_task: int = Field(default=10000, ge=0)
    default_model: str = Field(default="claude-sonnet-4-6", max_length=128)
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PoolOut(PoolIn):
    id: str
    org_id: str
    created_at: datetime


# ── artifact ────────────────────────────────────────────────────


class ArtifactOut(BaseModel):
    id: str
    run_id: str
    kind: str
    ref: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ── approval ────────────────────────────────────────────────────


class ApprovalOut(BaseModel):
    id: str
    task_id: str
    kind: str
    requested_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decision: str | None
    reason: str | None
    required_approvers: int
