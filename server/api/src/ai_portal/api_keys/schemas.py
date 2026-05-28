"""Pydantic schemas for the control-plane API keys domain."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list, max_length=64)
    expires_at: datetime | None = None
    actor_user_id: int | None = None


class ApiKeyOut(BaseModel):
    """Public shape — never carries the secret."""

    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID
    actor_user_id: int | None
    name: str
    prefix: str
    scopes: list[str] = Field(alias="scopes_json")
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    """Returned exactly once on POST /v1/api-keys. Carries the plaintext."""

    plaintext: str = Field(description="Full secret. Shown once at creation.")


class ApiKeyRotated(BaseModel):
    """Result of POST /v1/api-keys/{id}/rotate.

    Carries the new key (with plaintext) and the id of the revoked predecessor.
    """

    new_key: ApiKeyCreated
    revoked_id: _uuid.UUID
