"""Pydantic schemas for the gateway evals HTTP surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JudgeKind = Literal["exact", "regex", "llm", "custom"]


class EvalRecord(BaseModel):
    """One row in a test set."""

    id: str
    input: str
    expected: str = ""
    judge: JudgeKind = "exact"
    config: dict[str, Any] = Field(default_factory=dict)


class EvalTestSetIn(BaseModel):
    name: str
    records: list[EvalRecord] = Field(default_factory=list)


class EvalTestSetOut(BaseModel):
    id: str
    name: str
    records: list[EvalRecord]
    created_at: datetime
    updated_at: datetime


class EvalRunRowResult(BaseModel):
    """Per-record outcome of an eval run."""

    record_id: str
    passed: bool
    output: str = ""
    latency_ms: int = 0
    cost_cents: float = 0.0
    error: str | None = None


class EvalRunSummary(BaseModel):
    """Aggregated metrics for one ``(eval, target_model)`` run."""

    target_model: str
    pass_rate: float = 0.0
    p95_latency_ms: int = 0
    total_cost_cents: float = 0.0
    passed: int = 0
    failed: int = 0
    n: int = 0
    regression: bool = False
    regression_delta: float = 0.0


class EvalRunOut(BaseModel):
    id: str
    eval_id: str
    target_model: str
    summary: EvalRunSummary
    results: list[EvalRunRowResult]
    ran_at: datetime


class EvalRunRequest(BaseModel):
    """``POST /v1/gateway/evals/{id}/run`` body."""

    target_models: list[str] = Field(default_factory=list)
    judge_model: str | None = None  # used by llm-as-judge records
    regression_threshold: float = 0.05  # pass_rate drop > 5% → regression


class EvalRunResponse(BaseModel):
    runs: list[EvalRunOut]


__all__ = [
    "EvalRecord",
    "EvalRunOut",
    "EvalRunRequest",
    "EvalRunResponse",
    "EvalRunRowResult",
    "EvalRunSummary",
    "EvalTestSetIn",
    "EvalTestSetOut",
    "JudgeKind",
]
