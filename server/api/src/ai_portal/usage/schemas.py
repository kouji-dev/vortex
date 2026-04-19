"""Pydantic schemas for usage domain API responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class UsageSummaryRow(BaseModel):
    group_key: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: Decimal
    message_count: int


class UsageSummaryResponse(BaseModel):
    start: datetime
    end: datetime
    group_by: str
    rows: list[UsageSummaryRow]
    total_cost_usd: Decimal
    total_messages: int


class ConversationUsageResponse(BaseModel):
    conversation_id: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: Decimal
    message_count: int


class MyUsageResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    message_count: int
    quota_max_cost_usd: Decimal | None = None
    quota_pct: float | None = None
