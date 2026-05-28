"""Backward-compat shim. Use
:mod:`ai_portal.guardrails.gateway_shape.providers.llamaguard`.
"""

from ai_portal.guardrails.gateway_shape.providers.llamaguard import (
    LlamaGuardGuardrail,
)

__all__ = ["LlamaGuardGuardrail"]
