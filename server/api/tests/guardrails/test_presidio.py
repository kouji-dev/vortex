"""F2: Presidio PII guardrail.

We do not assume the real ``presidio-analyzer`` (and its spaCy model) is
installed in the test env — the heavy dependency is loaded lazily. These
tests inject a fake analyzer that mimics presidio's return shape so we
can exercise the redact / block / flag paths without the optional dep.

One integration test attempts the real analyzer and skips if it's not
available.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_portal.guardrails import GuardrailContext
from ai_portal.guardrails.providers.presidio import PresidioGuardrail

# ── fake analyzer ────────────────────────────────────────────────────────


@dataclass
class _FakeResult:
    entity_type: str
    start: int
    end: int
    score: float = 0.9


class _FakeAnalyzer:
    """Returns canned results by scanning for fixed substrings."""

    def __init__(self, hits: list[tuple[str, str]]):
        # list of (entity_type, substring)
        self._hits = hits
        self.calls = 0

    def analyze(self, *, text: str, entities=None, language="en"):
        self.calls += 1
        results: list[_FakeResult] = []
        for entity_type, substring in self._hits:
            if entities is not None and entity_type not in entities:
                continue
            idx = text.find(substring)
            if idx >= 0:
                results.append(
                    _FakeResult(
                        entity_type=entity_type,
                        start=idx,
                        end=idx + len(substring),
                        score=0.9,
                    )
                )
        return results


# ── tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_presidio_detects_email_and_phone_redact():
    fake = _FakeAnalyzer(
        [
            ("EMAIL_ADDRESS", "foo@bar.com"),
            ("PHONE_NUMBER", "+1-555-1234"),
        ]
    )
    g = PresidioGuardrail(analyzer=fake, mode="redact")
    v = await g.check_input(
        "email foo@bar.com and phone +1-555-1234 here",
        GuardrailContext(),
    )
    assert v.decision == "redact"
    assert "foo@bar.com" not in (v.redacted_text or "")
    assert "+1-555-1234" not in (v.redacted_text or "")
    assert "[REDACTED:EMAIL_ADDRESS]" in (v.redacted_text or "")
    assert "[REDACTED:PHONE_NUMBER]" in (v.redacted_text or "")
    kinds = {m.kind for m in v.matches}
    assert kinds == {"EMAIL_ADDRESS", "PHONE_NUMBER"}


@pytest.mark.asyncio
async def test_presidio_no_match_returns_allow():
    fake = _FakeAnalyzer([])
    g = PresidioGuardrail(analyzer=fake, mode="redact")
    v = await g.check_input("benign text", GuardrailContext())
    assert v.decision == "allow"


@pytest.mark.asyncio
async def test_presidio_block_mode():
    fake = _FakeAnalyzer([("CREDIT_CARD", "4111111111111111")])
    g = PresidioGuardrail(
        analyzer=fake,
        mode="block",
        entities=("CREDIT_CARD",),
    )
    v = await g.check_input(
        "card 4111111111111111 ok?",
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "CREDIT_CARD" for m in v.matches)


@pytest.mark.asyncio
async def test_presidio_flag_mode_records_without_editing():
    fake = _FakeAnalyzer([("PERSON", "Alice")])
    g = PresidioGuardrail(analyzer=fake, mode="flag")
    v = await g.check_input("hi Alice", GuardrailContext())
    assert v.decision == "flag"
    assert v.redacted_text is None


@pytest.mark.asyncio
async def test_presidio_threshold_filters_low_score_results():
    class _LowScoreAnalyzer:
        def analyze(self, *, text, entities=None, language="en"):
            return [_FakeResult(entity_type="EMAIL_ADDRESS", start=0, end=3, score=0.1)]

    g = PresidioGuardrail(analyzer=_LowScoreAnalyzer(), score_threshold=0.5)
    v = await g.check_input("any text", GuardrailContext())
    assert v.decision == "allow"


@pytest.mark.asyncio
async def test_presidio_real_analyzer_if_available():
    """Integration smoke test against the real Presidio engine.

    Skips if the package (or its spaCy model) isn't installed locally.
    """
    pytest.importorskip("presidio_analyzer")
    try:
        g = PresidioGuardrail(mode="redact", entities=("EMAIL_ADDRESS",))
        v = await g.check_input(
            "ping alice@example.com when ready",
            GuardrailContext(),
        )
    except Exception:  # spaCy model not installed
        pytest.skip("presidio runtime model missing")
    # Real analyzer should catch the email.
    assert v.decision in {"redact", "block"}
    assert any(m.kind == "EMAIL_ADDRESS" for m in v.matches)
