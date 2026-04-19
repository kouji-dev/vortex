"""Pydantic schemas for retention policy API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RetentionPolicyResponse(BaseModel):
    id: int
    org_id: UUID
    conversation_retention_days: int | None
    audit_retention_days: int
    usage_retention_days: int
    upload_retention_days: int | None
    legal_hold: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class RetentionPolicyUpdate(BaseModel):
    conversation_retention_days: int | None = None
    audit_retention_days: int = 2555
    usage_retention_days: int = 2555
    upload_retention_days: int | None = None
    legal_hold: bool = False
