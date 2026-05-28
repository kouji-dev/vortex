"""RAG eval runner.

Given a test set and a retrieval callable (and optional answer callable),
runs every record, scores retrieval metrics (recall@k, MRR, nDCG) and
optional answer metrics (LLM-as-judge), then aggregates a summary.

The runner is fully pluggable so it can be exercised in unit tests with
in-memory mocks — no DB, no HTTP, no LLM provider SDK imports.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Mapping

from ai_portal.rag.eval.metrics import (
    aggregate_mean,
    mrr,
    ndcg_at_k,
    recall_at_k,
)
from ai_portal.rag.eval.schemas import (
    EvalRecord,
    EvalRunRowResult,
    EvalRunSummary,
)

RetrieveFn = Callable[[str], Awaitable[list[str]]]
"""(query) -> list of retrieved doc ids ordered by score (descending)."""

AnswerFn = Callable[[str, list[str]], Awaitable[str]]
"""(query, retrieved doc ids) -> generated answer text."""

JudgeFn = Callable[[EvalRecord, str], Awaitable[Mapping[str, float]]]
"""(record, generated answer) -> {"correctness": x, "faithfulness": y}."""


@dataclass(slots=True)
class RunOutcome:
    """One run wrapped for persistence."""

    summary: EvalRunSummary
    results: list[EvalRunRowResult] = field(default_factory=list)


def _parse_judge_spec(judge: str) -> tuple[str, int | None]:
    """Parse ``recall@5`` → ``("recall", 5)``; ``mrr`` → ``("mrr", None)``."""
    if "@" in judge:
        name, _, k = judge.partition("@")
        try:
            return name.strip(), int(k)
        except ValueError:
            return name.strip(), None
    return judge.strip(), None


def score_record(
    record: EvalRecord,
    *,
    retrieved: list[str],
    judge_scores: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Compute every metric named on the record."""
    out: dict[str, float] = {}
    relevant = set(record.expected_doc_ids)
    grades = record.relevance_grades
    for spec in record.judges:
        name, k = _parse_judge_spec(spec)
        if name == "recall" and k is not None:
            out[spec] = recall_at_k(retrieved, relevant, k)
        elif name == "mrr":
            out[spec] = mrr(retrieved, relevant)
        elif name == "ndcg" and k is not None:
            out[spec] = ndcg_at_k(retrieved, grades, k)
        elif name in ("correctness", "faithfulness") and judge_scores:
            out[spec] = float(judge_scores.get(name, 0.0))
    return out


class EvalRunner:
    """Executes a test set against retrieve/answer callables."""

    def __init__(
        self,
        *,
        retrieve: RetrieveFn,
        answer: AnswerFn | None = None,
        judge: JudgeFn | None = None,
        regression_threshold: float = 0.05,
        primary_metric: str = "recall@5",
        pass_threshold: float = 0.5,
    ) -> None:
        self.retrieve = retrieve
        self.answer = answer
        self.judge = judge
        self.regression_threshold = regression_threshold
        self.primary_metric = primary_metric
        self.pass_threshold = pass_threshold

    async def run_record(self, record: EvalRecord) -> EvalRunRowResult:
        try:
            retrieved = await self.retrieve(record.query)
        except Exception as exc:  # noqa: BLE001
            return EvalRunRowResult(
                record_id=record.id,
                retrieved_doc_ids=[],
                metrics={},
                error=f"retrieve failed: {exc}",
            )
        gen_answer = ""
        judge_scores: dict[str, float] = {}
        if self.answer is not None:
            try:
                gen_answer = await self.answer(record.query, retrieved)
            except Exception as exc:  # noqa: BLE001
                return EvalRunRowResult(
                    record_id=record.id,
                    retrieved_doc_ids=retrieved,
                    metrics={},
                    error=f"answer failed: {exc}",
                )
            if self.judge is not None:
                try:
                    judge_scores = dict(await self.judge(record, gen_answer))
                except Exception as exc:  # noqa: BLE001
                    return EvalRunRowResult(
                        record_id=record.id,
                        retrieved_doc_ids=retrieved,
                        metrics={},
                        answer=gen_answer,
                        error=f"judge failed: {exc}",
                    )
        metrics = score_record(record, retrieved=retrieved, judge_scores=judge_scores)
        return EvalRunRowResult(
            record_id=record.id,
            retrieved_doc_ids=retrieved,
            metrics=metrics,
            answer=gen_answer,
            judge_scores=dict(judge_scores),
        )

    async def run(
        self,
        records: list[EvalRecord],
        *,
        previous_summary: EvalRunSummary | None = None,
    ) -> RunOutcome:
        results: list[EvalRunRowResult] = []
        for r in records:
            results.append(await self.run_record(r))
        # aggregate per-metric means
        keys: set[str] = set()
        for r in results:
            keys.update(r.metrics.keys())
        mean_metrics = {
            k: aggregate_mean([r.metrics.get(k, 0.0) for r in results]) for k in keys
        }
        primary = mean_metrics.get(self.primary_metric, 0.0)
        pass_rate = primary
        summary = EvalRunSummary(
            pass_rate=pass_rate,
            mean_metrics=mean_metrics,
            n=len(results),
        )
        summary = self.detect_regression(
            current=summary, previous=previous_summary
        )
        return RunOutcome(summary=summary, results=results)

    def detect_regression(
        self,
        *,
        current: EvalRunSummary,
        previous: EvalRunSummary | None,
    ) -> EvalRunSummary:
        """Flag a regression when ``pass_rate`` drops by more than threshold."""
        if previous is None:
            current.regression = False
            current.regression_delta = 0.0
            return current
        delta = current.pass_rate - previous.pass_rate
        current.regression_delta = delta
        current.regression = delta < -abs(self.regression_threshold)
        return current


__all__ = [
    "AnswerFn",
    "EvalRunner",
    "JudgeFn",
    "RetrieveFn",
    "RunOutcome",
    "score_record",
]
