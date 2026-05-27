"""Pydantic schemas for org control-plane endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrgCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
    region: str = Field(default="eu-west-1", max_length=32)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(
        default=None, min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$"
    )
    region: str | None = Field(default=None, max_length=32)


class OrgOut(BaseModel):
    id: str
    slug: str
    name: str
    region: str
    status: str
    instance_mode: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class OrgInviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="member", pattern=r"^(admin|member|viewer)$")


class OrgInviteOut(BaseModel):
    id: int
    org_id: str
    invited_email: str
    role: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgMemberOut(BaseModel):
    id: int
    org_id: str
    user_id: int
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
