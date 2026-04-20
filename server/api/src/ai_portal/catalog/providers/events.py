from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextDeltaEvent(_Base):
    type: Literal["text_delta"]
    text: str


class ThinkingDeltaEvent(_Base):
    type: Literal["thinking_delta"]
    text: str


class ToolCallRequestEvent(_Base):
    type: Literal["tool_call_request"]
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ServerToolUseEvent(_Base):
    type: Literal["server_tool_use"]
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class CitationEvent(_Base):
    type: Literal["citation"]
    url: str
    title: str | None = None
    snippet: str | None = None


class UsageEvent(_Base):
    type: Literal["usage"]
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    reasoning_tokens: int = 0


class IterationCompleteEvent(_Base):
    type: Literal["iteration_complete"]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "unknown"]


class ProviderErrorEvent(_Base):
    type: Literal["provider_error"]
    code: str
    message: str


ProviderStreamEventUnion = Annotated[
    TextDeltaEvent | ThinkingDeltaEvent | ToolCallRequestEvent |
    ServerToolUseEvent | CitationEvent | UsageEvent |
    IterationCompleteEvent | ProviderErrorEvent,
    Field(discriminator="type"),
]


class ProviderStreamEvent(RootModel[ProviderStreamEventUnion]):
    pass
