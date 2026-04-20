from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from ai_portal.chat.items import ErrorPayload, ThreadItemModel


class SseItemEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["item"]
    item: ThreadItemModel


class SseErrorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["error"]
    error: ErrorPayload


class SseDoneEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["done"]


SseEventUnion = Annotated[
    SseItemEvent | SseErrorEvent | SseDoneEvent,
    Field(discriminator="event_type"),
]


class SseEvent(RootModel[SseEventUnion]):
    pass
