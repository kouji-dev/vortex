"""Bundled guardrail provider implementations.

Each provider implements :class:`~ai_portal.guardrails.protocol.Guardrail`
and is wired into a policy bundle by name.
"""
from __future__ import annotations

from ai_portal.guardrails.providers.regex import RegexGuardrail
from ai_portal.guardrails.providers.secret_scanner import SecretScannerGuardrail

__all__ = ["RegexGuardrail", "SecretScannerGuardrail"]

# presidio is optional (heavy dep + spaCy model). Import lazily.
try:
    from ai_portal.guardrails.providers.presidio import (  # noqa: F401
        PresidioGuardrail,
    )

    __all__.append("PresidioGuardrail")
except ImportError:  # pragma: no cover
    PresidioGuardrail = None  # type: ignore[assignment]
