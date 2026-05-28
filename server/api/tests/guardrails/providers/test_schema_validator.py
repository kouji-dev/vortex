"""Tests for the JSON-schema validator guardrail."""

from __future__ import annotations

import json

import pytest

from ai_portal.guardrails.protocol import GuardrailCtx
from ai_portal.guardrails.providers.schema_validator import SchemaValidator

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}


@pytest.mark.asyncio
async def test_schema_validator_allows_valid_json() -> None:
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="block")
    ctx = GuardrailCtx()
    payload = json.dumps({"name": "Alice", "age": 30})
    verdict = await g.check_output(payload, ctx)
    assert verdict.decision == "allow"
    assert verdict.matches == []


@pytest.mark.asyncio
async def test_schema_validator_blocks_invalid_json() -> None:
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="block")
    ctx = GuardrailCtx()
    # age is wrong type
    payload = json.dumps({"name": "Bob", "age": "old"})
    verdict = await g.check_output(payload, ctx)
    assert verdict.decision == "block"
    assert verdict.matches  # at least one match
    assert "age" in (verdict.reason or "") or any(
        "age" in (m.detail or "") for m in verdict.matches
    )


@pytest.mark.asyncio
async def test_schema_validator_blocks_non_json_text() -> None:
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="block")
    ctx = GuardrailCtx()
    verdict = await g.check_output("not json at all", ctx)
    assert verdict.decision == "block"
    assert verdict.reason


@pytest.mark.asyncio
async def test_schema_validator_redact_returns_empty_object() -> None:
    """redact mode swaps invalid output for a stub instead of blocking."""
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="redact")
    ctx = GuardrailCtx()
    verdict = await g.check_output("garbage", ctx)
    assert verdict.decision == "redact"
    assert verdict.redacted_text is not None
    # redacted text must itself be valid JSON
    assert json.loads(verdict.redacted_text) == {}


@pytest.mark.asyncio
async def test_schema_validator_flag_does_not_block() -> None:
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="flag")
    ctx = GuardrailCtx()
    verdict = await g.check_output("garbage", ctx)
    assert verdict.decision == "flag"


@pytest.mark.asyncio
async def test_schema_validator_check_input_passthrough() -> None:
    """schema validation is output-side only; check_input always allows."""
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="block")
    verdict = await g.check_input("any input here", GuardrailCtx())
    assert verdict.decision == "allow"


@pytest.mark.asyncio
async def test_schema_validator_supports_ctx_schema_override() -> None:
    """ctx.config['schema'] takes precedence over constructor schema."""
    g = SchemaValidator(schema=PERSON_SCHEMA, on_violation="block")
    ctx = GuardrailCtx(config={"schema": {"type": "array"}})
    verdict = await g.check_output(json.dumps([1, 2, 3]), ctx)
    assert verdict.decision == "allow"


@pytest.mark.asyncio
async def test_schema_validator_name() -> None:
    g = SchemaValidator(schema=PERSON_SCHEMA)
    assert g.name == "schema_validator"
