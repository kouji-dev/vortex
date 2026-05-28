"""JSON-schema output validator guardrail.

Use cases:

- Enforce structured-output contracts even when the model ignores
  ``response_format``.
- Catch hallucinated extra fields under strict schemas.

Output-side only. ``check_input`` always allows — input validation is the
caller's job. Configuration:

- ``schema``: a JSON-schema dict (constructor) or ``ctx.config['schema']``
  override per-request.
- ``on_violation``: ``block`` (default) | ``redact`` | ``flag``. ``redact``
  swaps the bad output for an empty-object stub so downstream consumers see
  *something* parseable.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import jsonschema
from jsonschema import Draft202012Validator

from ai_portal.guardrails.protocol import (
    Decision,
    GuardrailCtx,
    Match,
    Verdict,
)


class SchemaValidator:
    """Validates response payload against a JSON Schema."""

    name = "schema_validator"

    def __init__(
        self,
        *,
        schema: dict[str, Any],
        on_violation: Literal["block", "redact", "flag"] = "block",
    ) -> None:
        self._default_schema = schema
        self._on_violation: Decision = on_violation

    async def check_input(self, prompt: str, ctx: GuardrailCtx) -> Verdict:
        """Input-side is a no-op for schema validation."""
        return Verdict(decision="allow")

    async def check_output(self, response: str, ctx: GuardrailCtx) -> Verdict:
        schema = ctx.config.get("schema", self._default_schema)
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as exc:
            return self._violation(
                reason=f"response is not valid JSON: {exc.msg}",
                matches=[Match(rule="json_parse", detail=str(exc))],
            )
        errors = sorted(
            Draft202012Validator(schema).iter_errors(parsed),
            key=lambda e: e.path,
        )
        if not errors:
            return Verdict(decision="allow")
        matches = [
            Match(
                rule="schema",
                detail=f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}",
            )
            for err in errors
        ]
        return self._violation(
            reason=f"schema validation failed ({len(errors)} error(s))",
            matches=matches,
        )

    def _violation(self, *, reason: str, matches: list[Match]) -> Verdict:
        if self._on_violation == "redact":
            return Verdict(
                decision="redact",
                matches=matches,
                redacted_text=json.dumps({}),
                reason=reason,
            )
        return Verdict(
            decision=self._on_violation,
            matches=matches,
            reason=reason,
        )


# protocol sanity: import-time check the class shape matches Guardrail
def _check_protocol() -> None:  # pragma: no cover
    from ai_portal.guardrails.protocol import Guardrail

    _: Guardrail = SchemaValidator(schema={})


__all__ = ["SchemaValidator"]
