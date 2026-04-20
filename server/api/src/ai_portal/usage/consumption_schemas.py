from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict


class KpiCard(BaseModel):
    label: str
    value: Decimal | int | str
    unit: str | None = None


class SummaryRow(BaseModel):
    key: str
    label: str
    messages: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    estimated_ratio: float


class SummaryResponse(BaseModel):
    kpis: list[KpiCard]
    by_model: list[SummaryRow]
    by_user: list[SummaryRow]
    by_provider: list[SummaryRow]
    by_capability: list[SummaryRow]
    by_tool: list[SummaryRow]


class TrendPoint(BaseModel):
    t: datetime
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    breakdown: dict[str, Decimal]


class TrendResponse(BaseModel):
    grain: Literal["day", "hour"]
    by: Literal["kind", "provider"]
    series: list[TrendPoint]


class ThreadRow(BaseModel):
    id: int
    title: str | None
    user_id: int
    model: str | None
    last_message_at: datetime | None
    total_cost_usd: Decimal
    total_items: int


class ThreadsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    rows: list[ThreadRow]


class TimelineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    turn_id: uuid.UUID | str
    kind: str
    status: str
    provider: str | None
    model: str | None
    cost_usd: Decimal | None
    cost_estimated: bool
    latency_ms: int | None
    data: dict
    created_at: datetime


class TimelineResponse(BaseModel):
    thread_id: int
    items: list[TimelineItem]
