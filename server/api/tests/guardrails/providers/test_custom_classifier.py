"""Tests for the custom-classifier guardrail."""

from __future__ import annotations

import pytest

from ai_portal.guardrails.protocol import GuardrailCtx, Verdict
from ai_portal.guardrails.providers.custom_classifier import (
    ClassifierResult,
    CustomClassifier,
)


# ── fakes ───────────────────────────────────────────────────────────────────


class FakeClassifier:
    """Sync fake classifier — returns score keyed on a substring."""

    def __init__(self, fixture: dict[str, float]) -> None:
        self.fixture = fixture
        self.calls: list[str] = []

    def __call__(self, text: str, *, model: str | None = None) -> ClassifierResult:
        self.calls.append(text)
        score = 0.0
        for needle, s in self.fixture.items():
            if needle in text:
                score = max(score, s)
        return ClassifierResult(score=score, label="bad" if score >= 0.5 else "ok")


class AsyncFakeClassifier:
    """Async variant — must also be supported."""

    def __init__(self, score: float) -> None:
        self.score = score
        self.calls: list[str] = []

    async def __call__(self, text: str, *, model: str | None = None) -> ClassifierResult:
        self.calls.append(text)
        return ClassifierResult(score=self.score, label="bad" if self.score >= 0.5 else "ok")


# ── tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_classifier_dispatches_to_configured_callable() -> None:
    fake = FakeClassifier({"forbidden": 0.9})
    g = CustomClassifier(classifier=fake, threshold=0.5)
    verdict = await g.check_input("This is a forbidden topic", GuardrailCtx())
    assert verdict.decision == "block"
    # classifier was actually called
    assert fake.calls == ["This is a forbidden topic"]
    assert any(m.rule == "custom_classifier" for m in verdict.matches)


@pytest.mark.asyncio
async def test_custom_classifier_below_threshold_allows() -> None:
    fake = FakeClassifier({"forbidden": 0.3})
    g = CustomClassifier(classifier=fake, threshold=0.5)
    verdict = await g.check_input("This is a forbidden topic", GuardrailCtx())
    assert verdict.decision == "allow"


@pytest.mark.asyncio
async def test_custom_classifier_supports_async_classifier() -> None:
    fake = AsyncFakeClassifier(score=0.8)
    g = CustomClassifier(classifier=fake, threshold=0.5)
    verdict = await g.check_input("whatever", GuardrailCtx())
    assert verdict.decision == "block"
    assert fake.calls == ["whatever"]


@pytest.mark.asyncio
async def test_custom_classifier_passes_model_to_callable() -> None:
    """Config carries a classifier_model that must reach the callable."""
    received_model = []

    def cls(text: str, *, model: str | None = None) -> ClassifierResult:
        received_model.append(model)
        return ClassifierResult(score=0.0, label="ok")

    g = CustomClassifier(classifier=cls, threshold=0.5, classifier_model="guard-v2")
    await g.check_input("x", GuardrailCtx())
    assert received_model == ["guard-v2"]


@pytest.mark.asyncio
async def test_custom_classifier_ctx_overrides_threshold() -> None:
    fake = FakeClassifier({"foo": 0.6})
    g = CustomClassifier(classifier=fake, threshold=0.9)  # would normally allow
    ctx = GuardrailCtx(config={"threshold": 0.5})
    verdict = await g.check_input("foo here", ctx)
    assert verdict.decision == "block"


@pytest.mark.asyncio
async def test_custom_classifier_redact_mode() -> None:
    fake = FakeClassifier({"foo": 0.9})
    g = CustomClassifier(classifier=fake, threshold=0.5, on_violation="redact")
    verdict = await g.check_input("foo present", GuardrailCtx())
    assert verdict.decision == "redact"
    # redacted text is not the original (must change somehow)
    assert verdict.redacted_text is not None


@pytest.mark.asyncio
async def test_custom_classifier_flag_mode_records_but_allows() -> None:
    fake = FakeClassifier({"foo": 0.9})
    g = CustomClassifier(classifier=fake, threshold=0.5, on_violation="flag")
    verdict = await g.check_input("foo here", GuardrailCtx())
    assert verdict.decision == "flag"
    assert any(m.rule == "custom_classifier" for m in verdict.matches)


@pytest.mark.asyncio
async def test_custom_classifier_check_output_uses_same_dispatch() -> None:
    fake = FakeClassifier({"bar": 0.9})
    g = CustomClassifier(classifier=fake, threshold=0.5)
    verdict = await g.check_output("response with bar in it", GuardrailCtx())
    assert verdict.decision == "block"
    assert fake.calls == ["response with bar in it"]


@pytest.mark.asyncio
async def test_custom_classifier_returns_score_in_verdict_detail() -> None:
    fake = FakeClassifier({"x": 0.75})
    g = CustomClassifier(classifier=fake, threshold=0.5)
    verdict = await g.check_input("x stuff", GuardrailCtx())
    # The score should be visible somewhere
    assert "0.75" in (verdict.reason or "") or any(
        "0.75" in (m.detail or "") for m in verdict.matches
    )


@pytest.mark.asyncio
async def test_custom_classifier_name() -> None:
    g = CustomClassifier(classifier=lambda t, model=None: ClassifierResult(score=0))
    assert g.name == "custom_classifier"


@pytest.mark.asyncio
async def test_custom_classifier_result_can_be_plain_float() -> None:
    """Callable may return a bare float for ergonomics."""

    def cls(text: str, *, model: str | None = None) -> float:
        return 0.7

    g = CustomClassifier(classifier=cls, threshold=0.5)
    verdict = await g.check_input("anything", GuardrailCtx())
    assert verdict.decision == "block"


@pytest.mark.asyncio
async def test_verdict_typed() -> None:
    """Sanity — returned object is the canonical Verdict."""
    g = CustomClassifier(classifier=lambda t, model=None: 0.1, threshold=0.5)
    verdict = await g.check_input("ok", GuardrailCtx())
    assert isinstance(verdict, Verdict)
