"""Eval runner — uses async mocks for retrieve/answer/judge callables."""
from __future__ import annotations

import pytest

from ai_portal.rag.eval.runner import EvalRunner, score_record
from ai_portal.rag.eval.schemas import EvalRecord, EvalRunSummary


def _record(id_: str, query: str, expected: list[str], judges: list[str]) -> EvalRecord:
    return EvalRecord(
        id=id_,
        query=query,
        expected_doc_ids=expected,
        judges=judges,
    )


def test_score_record_recall_only() -> None:
    rec = _record("q1", "x", ["a", "b"], ["recall@2"])
    m = score_record(rec, retrieved=["a", "c"])
    assert m["recall@2"] == 0.5


def test_score_record_mixed_metrics() -> None:
    rec = EvalRecord(
        id="q1",
        query="x",
        expected_doc_ids=["a"],
        relevance_grades={"a": 3, "b": 1},
        judges=["recall@5", "mrr", "ndcg@5"],
    )
    m = score_record(rec, retrieved=["a", "b", "c", "d", "e"])
    assert m["recall@5"] == 1.0
    assert m["mrr"] == 1.0
    assert m["ndcg@5"] > 0.0


@pytest.mark.asyncio
async def test_runner_happy_path_recall_only() -> None:
    async def retrieve(query: str) -> list[str]:
        return ["a", "b", "c"]

    runner = EvalRunner(retrieve=retrieve, primary_metric="recall@3")
    records = [
        _record("q1", "first", ["a"], ["recall@3"]),
        _record("q2", "second", ["b"], ["recall@3"]),
    ]
    outcome = await runner.run(records)
    assert outcome.summary.n == 2
    assert outcome.summary.pass_rate == 1.0
    assert outcome.summary.mean_metrics["recall@3"] == 1.0


@pytest.mark.asyncio
async def test_runner_retrieve_failure_records_error() -> None:
    async def retrieve(query: str) -> list[str]:
        raise RuntimeError("boom")

    runner = EvalRunner(retrieve=retrieve)
    records = [_record("q1", "x", ["a"], ["recall@5"])]
    outcome = await runner.run(records)
    assert outcome.results[0].error is not None
    assert "boom" in outcome.results[0].error


@pytest.mark.asyncio
async def test_runner_regression_flag_set_when_drop_exceeds_threshold() -> None:
    async def retrieve(query: str) -> list[str]:
        return ["x", "y"]  # no relevant doc

    runner = EvalRunner(
        retrieve=retrieve,
        regression_threshold=0.05,
        primary_metric="recall@2",
    )
    previous = EvalRunSummary(pass_rate=1.0, mean_metrics={"recall@2": 1.0}, n=1)
    records = [_record("q1", "x", ["a"], ["recall@2"])]
    outcome = await runner.run(records, previous_summary=previous)
    assert outcome.summary.pass_rate == 0.0
    assert outcome.summary.regression is True
    assert outcome.summary.regression_delta == -1.0


@pytest.mark.asyncio
async def test_runner_no_regression_when_no_previous_run() -> None:
    async def retrieve(query: str) -> list[str]:
        return []

    runner = EvalRunner(retrieve=retrieve)
    records = [_record("q1", "x", ["a"], ["recall@5"])]
    outcome = await runner.run(records, previous_summary=None)
    assert outcome.summary.regression is False
    assert outcome.summary.regression_delta == 0.0


@pytest.mark.asyncio
async def test_runner_with_answer_and_judge() -> None:
    async def retrieve(q: str) -> list[str]:
        return ["a", "b"]

    async def answer(q: str, docs: list[str]) -> str:
        return "an answer"

    async def judge(record, gen):
        return {"correctness": 0.7, "faithfulness": 0.9}

    runner = EvalRunner(
        retrieve=retrieve,
        answer=answer,
        judge=judge,
        primary_metric="correctness",
    )
    rec = EvalRecord(
        id="q1",
        query="x",
        expected_doc_ids=["a"],
        expected_answer="ans",
        judges=["recall@5", "correctness", "faithfulness"],
    )
    outcome = await runner.run([rec])
    row = outcome.results[0]
    assert row.answer == "an answer"
    assert row.judge_scores == {"correctness": 0.7, "faithfulness": 0.9}
    assert row.metrics["correctness"] == 0.7
    assert row.metrics["faithfulness"] == 0.9
    assert row.metrics["recall@5"] == 1.0
