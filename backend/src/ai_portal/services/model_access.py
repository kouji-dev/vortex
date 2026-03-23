"""Model allowlists, team grants, and provider fallbacks (future).

Call sites should go through this module so RBAC and catalog tables can plug in later
without reshaping HTTP handlers. Today: configured default + explicit request override.
"""

from __future__ import annotations

from ai_portal.config import Settings


def effective_chat_model(settings: Settings, requested: str | None) -> str:
    m = (requested or settings.chat_model).strip()
    if not m:
        raise ValueError("No chat model configured (CHAT_MODEL or per-request model)")
    return m
