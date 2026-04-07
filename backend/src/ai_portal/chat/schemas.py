"""Pydantic schemas for the chat domain."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Conversation settings (originally in schemas/conversation_settings.py)
# ---------------------------------------------------------------------------

class CapabilityToggles(BaseModel):
    """Feature toggles for a conversation (reflection / research / web / web_search / data_query)."""

    model_config = ConfigDict(extra="forbid")

    reflection: bool = False
    research: bool = False
    web: bool = False
    web_search: bool = False
    data_query: bool = False


class ConversationSettings(BaseModel):
    """
    Persisted in `chat_conversations.settings` (JSONB).
    Unknown keys in stored JSON are ignored on load (`extra='ignore'`).
    """

    model_config = ConfigDict(extra="ignore")

    capabilities: CapabilityToggles | None = None


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


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: Any
    extra: dict | None

    model_config = ConfigDict(from_attributes=True)


class MessagePatch(BaseModel):
    content: str = Field(min_length=1, max_length=500_000)


class ConversationKnowledgeBasesPut(BaseModel):
    knowledge_base_ids: list[int] = Field(default_factory=list)


class StreamMessageBody(BaseModel):
    content: str = Field(default="", max_length=500_000)
    regenerate_after_message_id: int | None = None
    model: str | None = Field(default=None, max_length=128)
    use_rag: bool = False

    @model_validator(mode="after")
    def content_or_regenerate(self) -> Self:
        if self.regenerate_after_message_id is None and not self.content.strip():
            raise ValueError("content is required unless regenerating a reply")
        return self


class CapabilityProfileEntryRead(BaseModel):
    description: str


class CapabilityProfileRead(BaseModel):
    reflection: CapabilityProfileEntryRead
    research: CapabilityProfileEntryRead
    web: CapabilityProfileEntryRead
    web_search: CapabilityProfileEntryRead
    data_query: CapabilityProfileEntryRead


class E2eSeedRagAssistantBody(BaseModel):
    kb_id: int
    kb_name: str = "Knowledge base"
    assistant_content: str = Field(
        default="This reply is grounded in your attached knowledge base (E2E seed).",
        max_length=500_000,
    )
