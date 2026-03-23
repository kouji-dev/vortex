"""Typed conversation settings stored as one JSON object (JSONB), not a separate table."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CapabilityToggles(BaseModel):
    """Feature toggles for a conversation (reflection / research / web)."""

    model_config = ConfigDict(extra="forbid")

    reflection: bool = False
    research: bool = False
    web: bool = False


class ConversationSettings(BaseModel):
    """
    Persisted in `chat_conversations.settings` (JSONB).
    Unknown keys in stored JSON are ignored on load (`extra='ignore'`).
    """

    model_config = ConfigDict(extra="ignore")

    capabilities: CapabilityToggles | None = None
