"""Backward-compat shim. Use
:mod:`ai_portal.guardrails.gateway_shape.providers.openai_moderation`.
"""

from ai_portal.guardrails.gateway_shape.providers.openai_moderation import (
    OpenAIModerationGuardrail,
)

__all__ = ["OpenAIModerationGuardrail"]
