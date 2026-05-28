"""Pydantic schemas for the RAG eval HTTP surface."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EvalRecord(BaseModel):
    """One test-set row.

    ``expected_doc_ids`` — binary relevance for recall@k / MRR.
    ``relevance_grades`` — graded relevance for nDCG (optional).
    ``expected_answer``  — gold answer for LLM-as-judge (optional).
    """

    id: str
    query: str
    expected_doc_ids: list[str] = Field(default_factory=list)
    relevance_grades: dict[str, int] = Field(default_factory=dict)
    expected_answer: str = ""
    judges: list[str] = Field(
        default_factory=lambda: ["recall@5", "mrr", "ndcg@10"]
    )


class EvalTestSetIn(BaseModel):
    name: str
    records: list[EvalRecord] = Field(default_factory=list)
    judge_model: str | None = None
    judge_temperature: float = 0.0


class EvalTestSetOut(BaseModel):
    id: _uuid.UUID
    kb_id: int
    name: str
    records: list[EvalRecord]
    judge_model: str | None = None
    judge_temperature: float = 0.0
    created_at: datetime
    updated_at: datetime


class EvalRunRowResult(BaseModel):
    """Per-record outcome (per-query metrics + retrieved doc ids)."""

    record_id: str
    retrieved_doc_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    answer: str = ""
    judge_scores: dict[str, float] = Field(default_factory=dict)
    error: str | None = None


class EvalRunSummary(BaseModel):
    """Aggregated metrics for a run (means across records)."""

    pass_rate: float = 0.0
    mean_metrics: dict[str, float] = Field(default_factory=dict)
    n: int = 0
    regression: bool = False
    regression_delta: float = 0.0


class EvalRunOut(BaseModel):
    id: _uuid.UUID
    eval_id: _uuid.UUID
    snapshot_id: str | None = None
    summary: EvalRunSummary
    results: list[EvalRunRowResult]
    regression: bool = False
    ran_at: datetime


class EvalRunRequest(BaseModel):
    """``POST /api/kbs/{id}/evals/{eid}/run`` body."""

    snapshot_id: str | None = None
    regression_threshold: float = 0.05
    primary_metric: str = "recall@5"


__all__ = [
    "EvalRecord",
    "EvalRunOut",
    "EvalRunRequest",
    "EvalRunRowResult",
    "EvalRunSummary",
    "EvalTestSetIn",
    "EvalTestSetOut",
]
