"""Backward-compat shim — re-exports from
:mod:`ai_portal.guardrails.gateway_shape.protocol`.

Single source of truth for the gateway-shape ``Verdict`` /
``Guardrail`` protocol now lives in the top-level guardrails package.
"""

from ai_portal.guardrails.gateway_shape.protocol import (
    Action,
    Guardrail,
    Hit,
    Verdict,
    clean,
)

__all__ = ["Guardrail", "Verdict", "Hit", "Action", "clean"]
