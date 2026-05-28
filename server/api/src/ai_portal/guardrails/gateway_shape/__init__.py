"""Gateway-shape guardrails — single text-payload ``scan`` API.

This sub-package owns the *gateway-shape* guardrails (the ``Verdict /
flagged / action / hits`` model). It is the consolidated home for what
used to live under ``ai_portal.gateway.guardrails`` so the top-level
``ai_portal.guardrails`` package is the single source of truth for all
guardrail providers.

Top-level ``ai_portal.guardrails`` keeps its own richer protocol
(``check_input`` / ``check_output`` with ``Decision``) for the
persistence-backed pipeline. The two APIs co-exist — pick the one that
matches your call site.

``ai_portal.gateway.guardrails`` re-exports everything here for backward
compat. New code should import from this package directly.
"""

from __future__ import annotations

from ai_portal.guardrails.gateway_shape.protocol import (
    Action,
    Guardrail,
    Hit,
    Verdict,
    clean,
)

__all__ = ["Guardrail", "Verdict", "Hit", "Action", "clean"]
