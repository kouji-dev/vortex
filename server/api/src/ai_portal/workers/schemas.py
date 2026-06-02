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


class PoolPatch(BaseModel):
    """Partial pool update — every field optional."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    template: str | None = Field(default=None, max_length=64)
    sandbox_provider: str | None = Field(default=None, max_length=32)
    repo_allow_list: list[str] | None = None
    budget_cents_per_task: int | None = Field(default=None, ge=0)
    default_model: str | None = Field(default=None, max_length=128)
    settings: dict[str, Any] | None = None
    enabled: bool | None = None


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
    state: str = "pending"
    approve_count: int = 0
    reject_count: int = 0
    approvers_decided: list[dict[str, Any]] = []


# ── worker instances (worker-centric "a worker IS a task") ───────


class SpawnWorkerBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    mode: str = Field(default="interactive", pattern="^(interactive|autonomous)$")
    runtime: str | None = Field(default=None, pattern="^(claude|codex)$")
    effort: str = Field(default="medium", pattern="^(low|medium|high|max)$")
    # GitLab connector config (project id/path, branch, token ref)
    connector: dict[str, Any] = Field(default_factory=dict)
    repo_url: str | None = Field(default=None, max_length=1024)
    pool_id: str | None = None
    skills: list[str] = Field(default_factory=list)
    trigger_source: str | None = Field(default=None, max_length=32)
    trigger_payload: dict[str, Any] = Field(default_factory=dict)


class WorkerOut(BaseModel):
    id: str
    org_id: str
    pool_id: str | None
    name: str
    state: str
    mode: str
    model: str
    runtime: str
    connector: dict[str, Any] = Field(default_factory=dict)
    repo_url: str | None
    sandbox_id: str | None
    trigger_source: str | None
    created_by: str | None
    created_at: datetime
    last_active_at: datetime | None


class WorkerMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=8192)


class InstanceRunOut(BaseModel):
    id: str
    worker_id: str
    seq_no: int
    user_message: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    cost_cents: int
    error: str | None


class RunChangeOut(BaseModel):
    id: str
    run_id: str
    file_path: str
    change_kind: str
    additions: int
    deletions: int
    diff_ref: str


class WorkerChatMessageOut(BaseModel):
    id: str
    worker_id: str
    run_id: str | None
    role: str
    content: str
    ts: datetime


class PermissionDecideBody(BaseModel):
    decision: str = Field(pattern="^(allow|deny)$")
    reason: str | None = Field(default=None, max_length=2048)
    updated_input: dict[str, Any] | None = None
