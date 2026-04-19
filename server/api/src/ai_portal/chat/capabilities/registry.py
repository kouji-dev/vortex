"""Capability registry — assembles system prompts and max iteration count.

The streaming service calls only these two functions; it never imports
individual capability modules.
"""

from __future__ import annotations

from ai_portal.chat.capabilities import reflection, research
from ai_portal.chat.schemas import ConversationSettings


def get_system_prompts(settings: ConversationSettings | None) -> list[str]:
    """Return system prompt strings for all enabled capabilities."""
    if settings is None or settings.capabilities is None:
        return []
    cap = settings.capabilities
    prompts: list[str] = []
    if cap.reflection:
        prompts.append(reflection.SYSTEM_PROMPT)
    if cap.research:
        prompts.append(research.SYSTEM_PROMPT)
    return prompts


def get_max_iterations(settings: ConversationSettings | None, base: int) -> int:
    """Return base * max(active multipliers), or base if no capability is active."""
    if settings is None or settings.capabilities is None:
        return base
    cap = settings.capabilities
    multipliers: list[int] = []
    if cap.reflection:
        multipliers.append(reflection.ITERATION_MULTIPLIER)
    if cap.research:
        multipliers.append(research.ITERATION_MULTIPLIER)
    if not multipliers:
        return base
    return base * max(multipliers)
