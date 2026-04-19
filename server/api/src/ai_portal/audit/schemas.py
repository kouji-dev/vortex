"""Pydantic schemas for audit log API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: int
    org_id: UUID
    actor_user_id: int | None
    actor_type: str
    event_type: str
    resource_type: str
    resource_id: str | None
    action: str
    metadata: dict | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditEventsResponse(BaseModel):
    total: int
    items: list[AuditEventResponse]
