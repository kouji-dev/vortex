"""Pydantic schemas for the webhooks domain."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookCreate(BaseModel):
    url: HttpUrl
    event_types: list[str] = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    event_types: list[str] | None = None
    description: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None


class WebhookOut(BaseModel):
    """Webhook payload returned to API clients (never includes secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID
    url: str
    event_types: list[str]
    enabled: bool
    description: str | None
    created_at: datetime
    disabled_at: datetime | None


class WebhookCreated(WebhookOut):
    """Returned exactly once on POST /v1/webhooks. Carries plaintext secret."""

    secret: str = Field(description="HMAC signing secret. Shown once on creation.")


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    webhook_id: _uuid.UUID
    event_id: _uuid.UUID
    event_type: str
    status: str
    attempts: int
    last_response_status: int | None
    last_response_body: str | None
    last_error: str | None
    next_attempt_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    created_at: datetime


class WebhookDeliveriesList(BaseModel):
    items: list[WebhookDeliveryOut]
    total: int


class WebhookEventTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    description: str
    module: str


class WebhookEventTypesList(BaseModel):
    items: list[WebhookEventTypeOut]
