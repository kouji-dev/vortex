"""F2: Secret scanner guardrail.

Covers (one canonical example per pattern):

- AWS access key blocked on input.
- AWS access + secret key pair flagged together.
- GitHub PAT, JWT, Slack token, OpenAI / Anthropic key, Google API key,
  Stripe live key, private key block.
- Benign text returns allow.
- Output mode defaults to redact (model leaked → editable).
"""

from __future__ import annotations

import pytest

from ai_portal.guardrails import GuardrailBlocked, GuardrailContext, GuardrailPipeline
from ai_portal.guardrails.providers.secret_scanner import SecretScannerGuardrail


@pytest.mark.asyncio
async def test_aws_access_key_blocked_on_input():
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "AWS_ACCESS_KEY" for m in v.matches)


@pytest.mark.asyncio
async def test_aws_access_plus_secret_detected_together():
    """When both are present we also catch the 40-char secret."""
    g = SecretScannerGuardrail()
    text = (
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    )
    v = await g.check_input(text, GuardrailContext())
    assert v.decision == "block"
    kinds = {m.kind for m in v.matches}
    assert "AWS_ACCESS_KEY" in kinds
    assert "AWS_SECRET_KEY" in kinds


@pytest.mark.asyncio
async def test_aws_secret_alone_not_reported():
    """40-char base64 alone is too false-positive — skipped unless access seen."""
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "random base64 wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY here",
        GuardrailContext(),
    )
    assert v.decision == "allow"


@pytest.mark.asyncio
async def test_github_pat_blocked():
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "token=ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "GITHUB_PAT" for m in v.matches)


@pytest.mark.asyncio
async def test_jwt_blocked():
    g = SecretScannerGuardrail()
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    v = await g.check_input(f"auth: {jwt}", GuardrailContext())
    assert v.decision == "block"
    assert any(m.kind == "JWT" for m in v.matches)


@pytest.mark.asyncio
async def test_slack_token_blocked():
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "slack=xoxb-12345-abcdef-ghijklmnopqrst",
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "SLACK_TOKEN" for m in v.matches)


@pytest.mark.asyncio
async def test_openai_key_blocked():
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "key=sk-abcdefghijklmnopqrstuvwxyz0123456789",
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "OPENAI_API_KEY" for m in v.matches)


@pytest.mark.asyncio
async def test_anthropic_key_blocked():
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "key=sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        GuardrailContext(),
    )
    assert v.decision == "block"
    kinds = {m.kind for m in v.matches}
    assert "ANTHROPIC_API_KEY" in kinds or "OPENAI_API_KEY" in kinds


@pytest.mark.asyncio
async def test_google_api_key_blocked():
    g = SecretScannerGuardrail()
    # 35-char tail after the AIza prefix.
    v = await g.check_input(
        "GOOG=AIza" + "a" * 35,
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "GOOGLE_API_KEY" for m in v.matches)


@pytest.mark.asyncio
async def test_stripe_live_key_blocked():
    g = SecretScannerGuardrail()
    v = await g.check_input(
        "STRIPE=sk_live_AbCdEf0123456789AbCdEf01",
        GuardrailContext(),
    )
    assert v.decision == "block"
    assert any(m.kind == "STRIPE_LIVE_KEY" for m in v.matches)


@pytest.mark.asyncio
async def test_private_key_block_detected():
    g = SecretScannerGuardrail()
    key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAv4cP9XaQ...AAA\n"
        "-----END RSA PRIVATE KEY-----"
    )
    v = await g.check_input(key, GuardrailContext())
    assert v.decision == "block"
    assert any(m.kind == "PRIVATE_KEY_BLOCK" for m in v.matches)


@pytest.mark.asyncio
async def test_benign_text_allowed():
    g = SecretScannerGuardrail()
    v = await g.check_input("just normal text no keys", GuardrailContext())
    assert v.decision == "allow"


@pytest.mark.asyncio
async def test_output_mode_default_redacts():
    """Default output mode is redact — model leaked, we edit it."""
    g = SecretScannerGuardrail()
    v = await g.check_output(
        "your key is AKIAIOSFODNN7EXAMPLE got it?",
        GuardrailContext(),
    )
    assert v.decision == "redact"
    assert "AKIAIOSFODNN7EXAMPLE" not in (v.redacted_text or "")
    assert "[REDACTED:AWS_ACCESS_KEY]" in (v.redacted_text or "")


@pytest.mark.asyncio
async def test_pipeline_blocks_on_secret_input():
    g = SecretScannerGuardrail()
    pipe = GuardrailPipeline.from_guardrails([g])
    with pytest.raises(GuardrailBlocked) as exc:
        await pipe.run_input(
            "leaking AKIAIOSFODNN7EXAMPLE here",
            GuardrailContext(),
        )
    assert exc.value.guardrail == "secret_scanner"


@pytest.mark.asyncio
async def test_input_mode_redact_swaps_text():
    g = SecretScannerGuardrail(input_mode="redact")
    v = await g.check_input(
        "key AKIAIOSFODNN7EXAMPLE then",
        GuardrailContext(),
    )
    assert v.decision == "redact"
    assert v.redacted_text == "key [REDACTED:AWS_ACCESS_KEY] then"
