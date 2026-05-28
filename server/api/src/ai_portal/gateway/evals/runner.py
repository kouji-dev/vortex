"""Eval runner — execute one test set against N target models.

For each ``(target_model, record)`` pair:

1. Build an :class:`LLMRequest` from ``record.input`` (single user message).
2. Dispatch through :func:`gateway.facade.complete`.
3. Score with the judge declared on the record.
4. Track latency + cost for aggregation.

Aggregation produces a per-model :class:`RunSummary` with ``pass_rate``,
``p95_latency_ms``, ``total_cost_cents``, and a ``regression`` flag computed
against the most recent prior run on the same eval+model when one is
provided to :meth:`EvalRunner.detect_regression`.
"""

from __future__ import annotations

import asyncio
import math
import time
import uuid as _uuid
from dataclasses import dataclass

from ai_portal.gateway import facade as gateway_facade
from ai_portal.gateway.evals.judges import (
    JudgeVerdict,
    custom_judge,
    exact_judge,
    llm_judge,
    regex_judge,
)
from ai_portal.gateway.evals.schemas import (
    EvalRecord,
    EvalRunRowResult,
    EvalRunSummary,
)
from ai_portal.gateway.facade import Actor
from ai_portal.gateway.pricing import compute_cost_cents
from ai_portal.gateway.types import LLMRequest, Message, TextBlock

# ── helpers ──────────────────────────────────────────────────────────────


def _response_text(content) -> str:
    parts: list[str] = []
    for block in content:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    return "".join(parts)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = max(0, math.ceil(len(s) * 0.95) - 1)
    return s[idx]


async def _score(
    record: EvalRecord,
    *,
    output: str,
    judge_actor: Actor | None,
) -> JudgeVerdict:
    kind = record.judge
    cfg = dict(record.config or {})
    if kind == "exact":
        return await exact_judge(output=output, expected=record.expected, config=cfg)
    if kind == "regex":
        return await regex_judge(output=output, expected=record.expected, config=cfg)
    if kind == "llm":
        return await llm_judge(
            output=output,
            expected=record.expected,
            config=cfg,
            actor=judge_actor,
        )
    if kind == "custom":
        return await custom_judge(output=output, expected=record.expected, config=cfg)
    return JudgeVerdict(passed=False, detail=f"unknown judge: {kind}")


# ── runner ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class RunOutcome:
    """One ``(eval, target_model)`` run wrapped for persistence."""

    target_model: str
    summary: EvalRunSummary
    results: list[EvalRunRowResult]


class EvalRunner:
    """Executes a test set across target models via the gateway facade."""

    def __init__(
        self,
        *,
        regression_threshold: float = 0.05,
    ) -> None:
        self.regression_threshold = regression_threshold

    async def run_record(
        self,
        *,
        record: EvalRecord,
        target_model: str,
        actor: Actor,
    ) -> EvalRunRowResult:
        """Execute one record against one model."""
        req = LLMRequest(
            model=target_model,
            messages=[
                Message(role="user", content=[TextBlock(text=record.input)]),
            ],
        )
        started = time.monotonic()
        try:
            resp = await gateway_facade.complete(req, actor)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - started) * 1000)
            return EvalRunRowResult(
                record_id=record.id,
                passed=False,
                output="",
                latency_ms=latency_ms,
                cost_cents=0.0,
                error=str(exc),
            )
        latency_ms = int((time.monotonic() - started) * 1000)
        output = _response_text(resp.content)

        verdict = await _score(record, output=output, judge_actor=actor)

        # Best-effort cost: pull pricing from the default facade hook.
        pricing = gateway_facade.get_default_facade().cfg.resolve_pricing(target_model)
        cost = compute_cost_cents(resp.usage, pricing) if pricing else 0.0

        return EvalRunRowResult(
            record_id=record.id,
            passed=verdict.passed,
            output=output,
            latency_ms=latency_ms,
            cost_cents=float(cost),
            error=None if verdict.passed else verdict.detail or None,
        )

    async def run(
        self,
        *,
        records: list[EvalRecord],
        target_model: str,
        actor: Actor,
    ) -> RunOutcome:
        """Run all records against one target model and aggregate metrics."""
        coros = [
            self.run_record(record=r, target_model=target_model, actor=actor)
            for r in records
        ]
        results: list[EvalRunRowResult] = await asyncio.gather(*coros) if coros else []
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        pass_rate = (passed / len(results)) if results else 0.0
        p95 = _p95([r.latency_ms for r in results])
        total_cost = sum(r.cost_cents for r in results)
        summary = EvalRunSummary(
            target_model=target_model,
            pass_rate=pass_rate,
            p95_latency_ms=p95,
            total_cost_cents=float(total_cost),
            passed=passed,
            failed=failed,
            n=len(results),
        )
        return RunOutcome(target_model=target_model, summary=summary, results=results)

    async def run_all(
        self,
        *,
        records: list[EvalRecord],
        target_models: list[str],
        actor: Actor,
    ) -> list[RunOutcome]:
        """Fan out one test set to N target models."""
        return [
            await self.run(records=records, target_model=m, actor=actor)
            for m in target_models
        ]

    # ── regression detection ────────────────────────────────────────────

    def detect_regression(
        self,
        *,
        current: EvalRunSummary,
        previous: EvalRunSummary | None,
    ) -> EvalRunSummary:
        """Flag ``current`` as a regression vs ``previous`` on pass_rate.

        Returns the same summary with ``regression`` + ``regression_delta``
        populated. ``previous`` of ``None`` (no prior run) → not a regression.
        """
        if previous is None:
            current.regression = False
            current.regression_delta = 0.0
            return current
        delta = current.pass_rate - previous.pass_rate
        current.regression_delta = delta
        current.regression = delta < -abs(self.regression_threshold)
        return current


# ── helpers for the service layer ────────────────────────────────────────


def make_actor_for_run(*, org_id: _uuid.UUID, user_id: int | None) -> Actor:
    return Actor(
        org_id=org_id,
        user_id=user_id,
        kind="user" if user_id is not None else "service",
    )


__all__ = [
    "EvalRunner",
    "RunOutcome",
    "make_actor_for_run",
]
