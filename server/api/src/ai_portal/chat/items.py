from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel

from ai_portal.chat.item_kinds import ItemRole, ItemStatus


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    thread_id: int
    turn_id: UUID
    role: ItemRole | None = None
    status: ItemStatus
    provider: str | None = None
    model: str | None = None
    cost_usd: Decimal | None = None
    cost_estimated: bool = False
    latency_ms: int | None = None
    parent_item_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class UserMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    attachments: list[dict] = Field(default_factory=list)


class AssistantTextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class LlmCallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    reasoning_tokens: int = 0
    iteration_index: int = 0


class ToolCallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    params: dict = Field(default_factory=dict)
    result_snippet: str | None = None
    error: str | None = None


class ServerToolUsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    input: dict = Field(default_factory=dict)


class ThinkingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class CitationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    title: str | None = None
    snippet: str | None = None


class MemoryPillPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int


class TurnEndPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["done", "error", "cancelled"]


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class UserMessageItem(_Base):
    kind: Literal["user_message"]
    data: UserMessagePayload


class AssistantTextItem(_Base):
    kind: Literal["assistant_text"]
    data: AssistantTextPayload


class LlmCallItem(_Base):
    kind: Literal["llm_call"]
    data: LlmCallPayload


class ToolCallItem(_Base):
    kind: Literal["tool_call"]
    data: ToolCallPayload


class ServerToolUseItem(_Base):
    kind: Literal["server_tool_use"]
    data: ServerToolUsePayload


class ThinkingItem(_Base):
    kind: Literal["thinking"]
    data: ThinkingPayload


class CitationItem(_Base):
    kind: Literal["citation"]
    data: CitationPayload


class MemoryPillItem(_Base):
    kind: Literal["memory_pill"]
    data: MemoryPillPayload


class TurnEndItem(_Base):
    kind: Literal["turn_end"]
    data: TurnEndPayload


class ErrorItem(_Base):
    kind: Literal["error"]
    data: ErrorPayload


ThreadItemUnion = Annotated[
    UserMessageItem | AssistantTextItem | LlmCallItem | ToolCallItem |
    ServerToolUseItem | ThinkingItem | CitationItem | MemoryPillItem |
    TurnEndItem | ErrorItem,
    Field(discriminator="kind"),
]


class ThreadItemModel(RootModel[ThreadItemUnion]):
    pass
