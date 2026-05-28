"""Pluggable classifier guardrail.

Config:

- ``classifier``: sync or async callable ``(text, *, model=None) -> result``.
  ``result`` may be a :class:`ClassifierResult`, a plain float, or any object
  exposing a ``score`` float attribute. Score >= threshold → violation.
- ``classifier_model``: identifier forwarded to the callable's ``model``
  kwarg — useful when the classifier dispatches to a hosted model.
- ``threshold``: 0.0–1.0 — strict ``>=`` triggers violation.
- ``on_violation``: ``block`` (default) | ``redact`` | ``flag``.

``ctx.config`` keys ``threshold`` / ``classifier_model`` override constructor
values per request, letting one policy bundle target different keys/routes
at different sensitivities.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from ai_portal.guardrails.protocol import (
    Decision,
    GuardrailCtx,
    Match,
    Verdict,
)


@dataclass(frozen=True)
class ClassifierResult:
    """Structured classifier output."""

    score: float
    label: str | None = None


@runtime_checkable
class _ClassifierCallable(Protocol):
    def __call__(
        self, text: str, *, model: str | None = None
    ) -> ClassifierResult | float | Any: ...


_PLACEHOLDER = "[REDACTED BY CLASSIFIER]"


def _coerce_score(result: Any) -> tuple[float, str | None]:
    """Normalise classifier output → (score, label)."""
    if isinstance(result, ClassifierResult):
        return result.score, result.label
    if isinstance(result, (int, float)):
        return float(result), None
    score = getattr(result, "score", None)
    if score is None:
        raise TypeError(f"classifier returned unsupported object: {type(result).__name__}")
    return float(score), getattr(result, "label", None)


class CustomClassifier:
    """Dispatches text to a configured callable classifier."""

    name = "custom_classifier"

    def __init__(
        self,
        *,
        classifier: _ClassifierCallable,
        threshold: float = 0.5,
        classifier_model: str | None = None,
        on_violation: Literal["block", "redact", "flag"] = "block",
    ) -> None:
        self._classifier = classifier
        self._threshold = threshold
        self._classifier_model = classifier_model
        self._on_violation: Decision = on_violation

    async def check_input(self, prompt: str, ctx: GuardrailCtx) -> Verdict:
        return await self._evaluate(prompt, ctx)

    async def check_output(self, response: str, ctx: GuardrailCtx) -> Verdict:
        return await self._evaluate(response, ctx)

    async def _evaluate(self, text: str, ctx: GuardrailCtx) -> Verdict:
        threshold = float(ctx.config.get("threshold", self._threshold))
        model = ctx.config.get("classifier_model", self._classifier_model)

        raw = self._classifier(text, model=model)
        if inspect.isawaitable(raw):
            raw = await raw
        score, label = _coerce_score(raw)

        if score < threshold:
            return Verdict(decision="allow")

        match = Match(
            rule="custom_classifier",
            detail=f"score={score:.2f}, label={label!r}, threshold={threshold:.2f}",
        )
        reason = (
            f"classifier score {score:.2f} >= threshold {threshold:.2f}"
            + (f" (label={label!r})" if label else "")
        )

        if self._on_violation == "redact":
            return Verdict(
                decision="redact",
                matches=[match],
                redacted_text=_PLACEHOLDER,
                reason=reason,
            )
        return Verdict(
            decision=self._on_violation,
            matches=[match],
            reason=reason,
        )


def _check_protocol() -> None:  # pragma: no cover
    from ai_portal.guardrails.protocol import Guardrail

    _: Guardrail = CustomClassifier(classifier=lambda t, model=None: 0.0)


__all__ = ["ClassifierResult", "CustomClassifier"]
