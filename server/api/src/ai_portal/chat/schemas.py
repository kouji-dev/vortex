"""Pydantic schemas for the chat domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus


# ---------------------------------------------------------------------------
# Conversation settings (originally in schemas/conversation_settings.py)
# ---------------------------------------------------------------------------

class CapabilityToggles(BaseModel):
    """Feature toggles for a conversation (reflection / research)."""

    model_config = ConfigDict(extra="ignore")

    reflection: bool = False
    research: bool = False


class ConversationSettings(BaseModel):
    """
    Persisted in `chat_conversations.settings` (JSONB).
    Unknown keys in stored JSON are ignored on load (`extra='ignore'`).
    """

    model_config = ConfigDict(extra="ignore")

    capabilities: CapabilityToggles | None = None


# ---------------------------------------------------------------------------
# Thread / ThreadItem read schemas (Task 1.6)
# ---------------------------------------------------------------------------

class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: UUID
    user_id: int
    assistant_id: int | None
    title: str | None
    model: str | None
    summary: str | None
    last_message_at: datetime | None
    created_at: datetime


class ThreadItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    turn_id: UUID
    kind: ItemKind
    role: ItemRole | None
    status: ItemStatus
    provider: str | None
    model: str | None
    cost_usd: Decimal | None
    cost_estimated: bool
    latency_ms: int | None
    data: dict[str, Any]
    parent_item_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Request / response schemas (originally in api/conversations.py)
# ---------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=128)
    assistant_id: int | None = None
    settings: ConversationSettings | None = None
    knowledge_base_ids: list[int] = Field(default_factory=list)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=128)
    assistant_id: int | None = None
    settings: ConversationSettings | None = None


class ConversationRead(BaseModel):
    id: int
    user_id: int
    assistant_id: int | None
    title: str | None
    model: str | None
    settings: ConversationSettings | None
    created_at: Any
    knowledge_base_ids: list[int] = Field(default_factory=list)


class ConversationKnowledgeBasesPut(BaseModel):
    knowledge_base_ids: list[int] = Field(default_factory=list)


class StreamMessageBody(BaseModel):
    content: str = Field(default="", max_length=500_000)
    regenerate_after_message_id: int | None = None
    model: str | None = Field(default=None, max_length=128)
    use_rag: bool = False
    attachment_ids: list[int] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def content_or_regenerate(self) -> Self:
        if self.regenerate_after_message_id is None and not self.content.strip():
            raise ValueError("content is required unless regenerating a reply")
        return self


class ChatUploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    size_bytes: int
    content_type: str | None = None


class CapabilityProfileEntryRead(BaseModel):
    description: str


class CapabilityProfileRead(BaseModel):
    reflection: CapabilityProfileEntryRead
    research: CapabilityProfileEntryRead


