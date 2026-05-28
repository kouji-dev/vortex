"""Policy validators — pure-logic checks for guardrail policy bundles.

Used by the live-test endpoint (J6) before instantiating any providers,
and by the policy CRUD endpoints before writing to the DB. Pure-logic so
they're cheap to unit test and they fail fast on malformed input.

Bundle shape mirrors the frontend ``GuardrailBundle``::

    {
      "input":  [{"kind": "regex", "config": {...}, "on_match": "block"}, …],
      "output": [...]
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Keep in sync with apps/frontend/src/lib/gateway-types.ts.
VALID_KINDS = frozenset(
    {
        "regex",
        "presidio",
        "openai_moderation",
        "llamaguard",
        "prompt_injection_classifier",
        "secret_scanner",
        "topic_filter",
        "schema_validator",
        "custom_classifier",
    }
)

VALID_ACTIONS = frozenset({"allow", "redact", "block", "flag"})

VALID_PHASES = frozenset({"input", "output"})

# Strongest-wins ordering (matches frontend resolveFinalDecision).
ACTION_PRIORITY: dict[str, int] = {
    "allow": 0,
    "flag": 1,
    "redact": 2,
    "block": 3,
}


@dataclass(frozen=True)
class ValidationError:
    """One issue in a bundle. ``path`` is dotted, e.g. ``input[0].kind``."""

    path: str
    message: str


def validate_step(step: object, *, path: str) -> list[ValidationError]:
    """Return a list of issues with a single step. Empty list = ok."""
    errs: list[ValidationError] = []
    if not isinstance(step, dict):
        errs.append(ValidationError(path, "step must be an object"))
        return errs

    kind = step.get("kind")
    if not isinstance(kind, str) or not kind:
        errs.append(ValidationError(f"{path}.kind", "kind is required (string)"))
    elif kind not in VALID_KINDS:
        errs.append(
            ValidationError(
                f"{path}.kind",
                f"unknown kind '{kind}' — valid: {sorted(VALID_KINDS)}",
            )
        )

    on_match = step.get("on_match", "allow")
    if not isinstance(on_match, str) or on_match not in VALID_ACTIONS:
        errs.append(
            ValidationError(
                f"{path}.on_match",
                f"on_match must be one of {sorted(VALID_ACTIONS)}",
            )
        )

    config = step.get("config", {})
    if not isinstance(config, dict):
        errs.append(ValidationError(f"{path}.config", "config must be an object"))

    return errs


def validate_phase(steps: object, *, phase: str) -> list[ValidationError]:
    """Validate one phase's list of steps."""
    errs: list[ValidationError] = []
    if steps is None:
        return errs  # phase is optional
    if not isinstance(steps, list):
        errs.append(ValidationError(phase, f"{phase} must be a list"))
        return errs
    for i, step in enumerate(steps):
        errs.extend(validate_step(step, path=f"{phase}[{i}]"))
    return errs


def validate_bundle(bundle: object) -> list[ValidationError]:
    """Return a list of issues for a whole bundle. Empty list = ok.

    Empty bundles (no input + no output) are valid — that's an
    explicitly-empty policy that allows everything.
    """
    errs: list[ValidationError] = []
    if not isinstance(bundle, dict):
        errs.append(ValidationError("", "bundle must be an object"))
        return errs

    extra = set(bundle.keys()) - VALID_PHASES
    for key in sorted(extra):
        errs.append(ValidationError(key, f"unknown phase '{key}'"))

    errs.extend(validate_phase(bundle.get("input"), phase="input"))
    errs.extend(validate_phase(bundle.get("output"), phase="output"))
    return errs


def is_valid(bundle: object) -> bool:
    return not validate_bundle(bundle)


def resolve_final_decision(decisions: list[str]) -> str:
    """Strongest-wins reducer — matches frontend logic exactly.

    Unknown action strings are treated as ``allow``.
    """
    best = "allow"
    best_pri = ACTION_PRIORITY[best]
    for d in decisions:
        pri = ACTION_PRIORITY.get(d, 0)
        if pri > best_pri:
            best = d
            best_pri = pri
    return best


__all__ = [
    "ACTION_PRIORITY",
    "VALID_ACTIONS",
    "VALID_KINDS",
    "VALID_PHASES",
    "ValidationError",
    "is_valid",
    "resolve_final_decision",
    "validate_bundle",
    "validate_phase",
    "validate_step",
]


def normalize_bundle(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return a canonical-shape bundle. Defaults missing phases to ``[]``.

    Assumes the bundle has already passed :func:`validate_bundle`.
    """
    return {
        "input": list(bundle.get("input") or []),
        "output": list(bundle.get("output") or []),
    }
