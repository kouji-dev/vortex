"""Tests for the topic-filter guardrail."""

from __future__ import annotations

import pytest

from ai_portal.guardrails.protocol import GuardrailCtx
from ai_portal.guardrails.providers.topic_filter import TopicFilter


@pytest.mark.asyncio
async def test_topic_filter_denies_sentence_about_denied_topic() -> None:
    """Sentence whose terms hit the deny list returns ``block``."""
    g = TopicFilter(deny=["weapons", "firearms"])
    verdict = await g.check_input(
        "How do I assemble homemade firearms quickly?",
        GuardrailCtx(),
    )
    assert verdict.decision == "block"
    assert any(m.rule == "topic_deny" for m in verdict.matches)
    assert "firearms" in (verdict.reason or "").lower()


@pytest.mark.asyncio
async def test_topic_filter_allows_clean_sentence() -> None:
    g = TopicFilter(deny=["weapons", "firearms"])
    verdict = await g.check_input(
        "What's the weather like in Paris today?",
        GuardrailCtx(),
    )
    assert verdict.decision == "allow"


@pytest.mark.asyncio
async def test_topic_filter_allow_list_restricts_to_listed_topics() -> None:
    """When ``allow`` is set, only sentences mentioning those topics pass."""
    g = TopicFilter(allow=["python", "sql"])
    on = await g.check_input("How do I write a python function?", GuardrailCtx())
    assert on.decision == "allow"
    off = await g.check_input("What is the meaning of life?", GuardrailCtx())
    assert off.decision == "block"
    assert any(m.rule == "topic_allow_miss" for m in off.matches)


@pytest.mark.asyncio
async def test_topic_filter_deny_beats_allow() -> None:
    """A denied term blocks even if an allowed term also matches."""
    g = TopicFilter(allow=["python"], deny=["malware"])
    verdict = await g.check_input(
        "Write python that builds malware payloads",
        GuardrailCtx(),
    )
    assert verdict.decision == "block"
    assert any(m.rule == "topic_deny" for m in verdict.matches)


@pytest.mark.asyncio
async def test_topic_filter_case_insensitive() -> None:
    g = TopicFilter(deny=["BombMaking"])
    verdict = await g.check_input("explain bombmaking", GuardrailCtx())
    assert verdict.decision == "block"


@pytest.mark.asyncio
async def test_topic_filter_word_boundary() -> None:
    """Substring match inside a larger word should NOT trigger."""
    g = TopicFilter(deny=["arm"])
    verdict = await g.check_input("My alarm clock is broken", GuardrailCtx())
    # ``arm`` inside ``alarm`` should not match — boundary-aware
    assert verdict.decision == "allow"


@pytest.mark.asyncio
async def test_topic_filter_redact_mode() -> None:
    """redact mode rewrites the denied term to a placeholder."""
    g = TopicFilter(deny=["firearms"], on_violation="redact")
    verdict = await g.check_input("buy firearms cheap", GuardrailCtx())
    assert verdict.decision == "redact"
    assert verdict.redacted_text is not None
    assert "firearms" not in verdict.redacted_text.lower()


@pytest.mark.asyncio
async def test_topic_filter_checks_output_too() -> None:
    g = TopicFilter(deny=["firearms"])
    verdict = await g.check_output("here is how to acquire firearms", GuardrailCtx())
    assert verdict.decision == "block"


@pytest.mark.asyncio
async def test_topic_filter_ctx_override() -> None:
    """ctx.config can override deny/allow per-request."""
    g = TopicFilter(deny=["foo"])
    ctx = GuardrailCtx(config={"deny": ["bar"]})
    v1 = await g.check_input("talking about bar topics", ctx)
    assert v1.decision == "block"
    v2 = await g.check_input("talking about foo topics", ctx)
    # ctx override replaced the deny list; foo no longer blocked
    assert v2.decision == "allow"


@pytest.mark.asyncio
async def test_topic_filter_name() -> None:
    g = TopicFilter(deny=["x"])
    assert g.name == "topic_filter"
