"""F2: Regex guardrail provider.

Covers:

- Pattern list matches on input + redacts substrings.
- Block mode raises via pipeline.
- Flag mode records without editing.
- Custom placeholder formatting.
"""

from __future__ import annotations

import pytest

from ai_portal.guardrails import GuardrailContext
from ai_portal.guardrails.providers.regex import RegexGuardrail


@pytest.mark.asyncio
async def test_regex_redact_replaces_email_matches():
    g = RegexGuardrail(
        patterns=[("EMAIL", r"[\w.-]+@[\w.-]+\.\w+")],
        mode="redact",
        placeholder="[REDACTED:{kind}]",
    )
    v = await g.check_input("contact me at foo@bar.com please", GuardrailContext())
    assert v.decision == "redact"
    assert v.redacted_text == "contact me at [REDACTED:EMAIL] please"
    assert len(v.matches) == 1
    assert v.matches[0].kind == "EMAIL"
    assert v.matches[0].snippet == "foo@bar.com"


@pytest.mark.asyncio
async def test_regex_no_match_returns_allow():
    g = RegexGuardrail(patterns=[("X", r"NOTHERE")], mode="redact")
    v = await g.check_input("plain text", GuardrailContext())
    assert v.decision == "allow"


@pytest.mark.asyncio
async def test_regex_block_mode_returns_block_verdict():
    g = RegexGuardrail(
        patterns=[("FORBIDDEN", r"BANNED")],
        mode="block",
    )
    v = await g.check_input("this contains BANNED words", GuardrailContext())
    assert v.decision == "block"
    assert "FORBIDDEN" in v.reason


@pytest.mark.asyncio
async def test_regex_flag_mode_records_without_editing():
    g = RegexGuardrail(
        patterns=[("WARN", r"warn")],
        mode="flag",
    )
    v = await g.check_input("warn me", GuardrailContext())
    assert v.decision == "flag"
    assert v.redacted_text is None
    assert v.matches[0].kind == "WARN"


@pytest.mark.asyncio
async def test_regex_multiple_matches_redacted_in_order():
    g = RegexGuardrail(
        patterns=[("CC", r"\d{4}")],
        mode="redact",
        placeholder="****",
    )
    v = await g.check_input("nums 1234 and 5678", GuardrailContext())
    assert v.decision == "redact"
    assert v.redacted_text == "nums **** and ****"
    assert len(v.matches) == 2


@pytest.mark.asyncio
async def test_regex_check_phase_input_only():
    g = RegexGuardrail(
        patterns=[("X", r"X")],
        mode="block",
        check_phase="input",
    )
    blocked = await g.check_input("X here", GuardrailContext())
    assert blocked.decision == "block"
    skipped = await g.check_output("X here", GuardrailContext())
    assert skipped.decision == "allow"


@pytest.mark.asyncio
async def test_regex_integrates_with_pipeline_redact():
    """End-to-end: pipeline calls regex, gets redacted text, passes on."""
    from ai_portal.guardrails import GuardrailPipeline

    g = RegexGuardrail(
        patterns=[("EMAIL", r"[\w.-]+@[\w.-]+\.\w+")],
        mode="redact",
        placeholder="<email>",
    )
    pipe = GuardrailPipeline.from_guardrails([g])
    res = await pipe.run_input("hi foo@bar.com bye", GuardrailContext())
    assert res.blocked is False
    assert res.text == "hi <email> bye"
    assert len(res.violations) == 1
