"""Moderation guardrail tests (F4).

These guardrails wrap a :class:`Moderator` provider and adapt its
``ModerationResult`` into a :class:`Verdict`. The Moderator itself
is gateway-routed (OpenAI / LlamaGuard self-hosted).

Tests use an in-memory fake ``Moderator`` — no HTTP. The HTTP path
for each underlying Moderator is already covered by
``tests/gateway/moderations/test_providers.py``.
"""

from __future__ import annotations

import pytest

from ai_portal.gateway.moderations.protocol import (
    CATEGORIES,
    ModerationResult,
    empty_result,
)


class _FakeModerator:
    """Replays canned :class:`ModerationResult` per input position."""

    def __init__(self, results: list[ModerationResult], name: str = "fake") -> None:
        self.name = name
        self._results = results
        self.calls: list[list[str]] = []

    async def moderate(
        self, inputs: list[str], *, model: str | None = None
    ) -> list[ModerationResult]:
        self.calls.append(inputs)
        return self._results[: len(inputs)] or [empty_result()] * len(inputs)


def _hate_result() -> ModerationResult:
    cats = {c: False for c in CATEGORIES}
    scores = {c: 0.0 for c in CATEGORIES}
    cats["hate"] = True
    scores["hate"] = 0.94
    return ModerationResult(flagged=True, categories=cats, category_scores=scores)


def _clean_result() -> ModerationResult:
    return ModerationResult(
        flagged=False,
        categories={c: False for c in CATEGORIES},
        category_scores={c: 0.01 for c in CATEGORIES},
    )


# ── OpenAI-moderation guardrail wrapper ─────────────────────────────────


@pytest.mark.asyncio
async def test_openai_moderation_guardrail_flags_hate():
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail,
    )

    g = OpenAIModerationGuardrail(moderator=_FakeModerator([_hate_result()]))
    v = await g.scan("I hate <group>.")
    assert v.flagged is True
    assert v.action == "block"
    assert any(h.category == "hate" for h in v.hits)
    assert v.metadata["provider"] == "openai_moderation"


@pytest.mark.asyncio
async def test_openai_moderation_guardrail_passes_clean():
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail,
    )

    g = OpenAIModerationGuardrail(moderator=_FakeModerator([_clean_result()]))
    v = await g.scan("Hello, world.")
    assert v.flagged is False
    assert v.action == "allow"
    assert v.hits == []


@pytest.mark.asyncio
async def test_openai_moderation_guardrail_uses_category_threshold():
    """Below-threshold flagged categories don't pollute hits."""
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail,
    )

    cats = {c: False for c in CATEGORIES}
    scores = {c: 0.0 for c in CATEGORIES}
    scores["hate"] = 0.3  # below threshold 0.5
    scores["violence"] = 0.8
    cats["violence"] = True
    result = ModerationResult(flagged=True, categories=cats, category_scores=scores)
    g = OpenAIModerationGuardrail(
        moderator=_FakeModerator([result]), threshold=0.5
    )
    v = await g.scan("...")
    assert v.flagged is True
    categories_hit = {h.category for h in v.hits}
    assert "violence" in categories_hit
    assert "hate" not in categories_hit


@pytest.mark.asyncio
async def test_openai_moderation_guardrail_provider_name():
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail,
    )

    g = OpenAIModerationGuardrail(moderator=_FakeModerator([_clean_result()]))
    assert g.name == "openai_moderation"


@pytest.mark.asyncio
async def test_openai_moderation_guardrail_passes_model_through():
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail,
    )

    class Spy(_FakeModerator):
        def __init__(self) -> None:
            super().__init__([_clean_result()])
            self.received_model: str | None = None

        async def moderate(self, inputs, *, model=None):
            self.received_model = model
            return await super().moderate(inputs, model=model)

    spy = Spy()
    g = OpenAIModerationGuardrail(moderator=spy, model="omni-moderation-latest")
    await g.scan("x")
    assert spy.received_model == "omni-moderation-latest"


# ── LlamaGuard guardrail wrapper ────────────────────────────────────────


@pytest.mark.asyncio
async def test_llamaguard_guardrail_flags_unsafe():
    from ai_portal.gateway.guardrails.providers.llamaguard import (
        LlamaGuardGuardrail,
    )

    cats = {c: False for c in CATEGORIES}
    cats["violence"] = True
    cats["harassment"] = True
    scores = {c: (1.0 if cats[c] else 0.0) for c in CATEGORIES}
    res = ModerationResult(flagged=True, categories=cats, category_scores=scores)
    g = LlamaGuardGuardrail(moderator=_FakeModerator([res], name="llamaguard"))
    v = await g.scan("violent content")
    assert v.flagged is True
    assert v.action == "block"
    cats_hit = {h.category for h in v.hits}
    assert "violence" in cats_hit
    assert "harassment" in cats_hit
    assert v.metadata["provider"] == "llamaguard"


@pytest.mark.asyncio
async def test_llamaguard_guardrail_passes_safe():
    from ai_portal.gateway.guardrails.providers.llamaguard import (
        LlamaGuardGuardrail,
    )

    g = LlamaGuardGuardrail(
        moderator=_FakeModerator([_clean_result()], name="llamaguard")
    )
    v = await g.scan("a normal hello")
    assert v.flagged is False
    assert v.action == "allow"


@pytest.mark.asyncio
async def test_llamaguard_guardrail_provider_name():
    from ai_portal.gateway.guardrails.providers.llamaguard import (
        LlamaGuardGuardrail,
    )

    g = LlamaGuardGuardrail(moderator=_FakeModerator([_clean_result()]))
    assert g.name == "llamaguard"


# ── Empty / edge cases ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_results_passes():
    from ai_portal.gateway.guardrails.providers.openai_moderation import (
        OpenAIModerationGuardrail,
    )

    class Empty(_FakeModerator):
        async def moderate(self, inputs, *, model=None):
            return []

    g = OpenAIModerationGuardrail(moderator=Empty([]))
    v = await g.scan("anything")
    assert v.flagged is False
    assert v.action == "allow"
