"""Backward-compat shim. Use
:mod:`ai_portal.guardrails.gateway_shape.providers.prompt_injection`.
"""

from ai_portal.guardrails.gateway_shape.providers.prompt_injection import (
    PromptInjectionGuardrail,
)

__all__ = ["PromptInjectionGuardrail"]
