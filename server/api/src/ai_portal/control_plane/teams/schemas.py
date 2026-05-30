"""Pydantic schemas for the Teams sub-domain."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_SLUG_RE = r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"


class TeamCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=_SLUG_RE)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class TeamPatch(BaseModel):
    slug: str | None = Field(default=None, max_length=64, pattern=_SLUG_RE)
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID
    slug: str
    name: str
    description: str | None
    created_at: datetime
    archived_at: datetime | None
    member_count: int = 0


class TeamMemberAdd(BaseModel):
    user_id: int
    role: str | None = Field(default=None, max_length=32)


class TeamMemberPatch(BaseModel):
    role: str | None = Field(default=None, max_length=32)


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: _uuid.UUID
    user_id: int
    email: str | None = None
    name: str | None = None
    role: str | None
    created_at: datetime


class TeamKeyCount(BaseModel):
    """Per-team API-key aggregation. Keys remain user-owned."""

    team_id: _uuid.UUID
    member_count: int
    key_count: int


class TeamUsage(BaseModel):
    """Team usage aggregated across the team's members.

    Spend + tokens are summed over ``usage_rollup`` rows for every member's
    ``user_id`` within the requested window.
    """

    team_id: _uuid.UUID
    member_count: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: float
    message_count: int
