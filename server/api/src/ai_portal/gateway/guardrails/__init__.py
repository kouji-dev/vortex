"""Backward-compat shim — guardrails now live under
:mod:`ai_portal.guardrails.gateway_shape`.

Re-exports the gateway-shape protocol (``Verdict``/``Hit``/``Action``/
``Guardrail``/``clean``) from the consolidated location so existing
imports keep working. New code should import from
:mod:`ai_portal.guardrails.gateway_shape` directly.
"""

from ai_portal.guardrails.gateway_shape import (
    Action,
    Guardrail,
    Hit,
    Verdict,
    clean,
)

__all__ = ["Guardrail", "Verdict", "Hit", "Action", "clean"]
