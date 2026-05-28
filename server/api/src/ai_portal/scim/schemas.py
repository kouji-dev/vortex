"""Pydantic schemas for SCIM admin routes + group-role mapping.

The SCIM 2.0 wire format itself is handled by :mod:`scim2_models` —
these schemas describe the *admin* surface (creating endpoints, mapping
groups to roles) and the responses we send back to admin UI clients.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PresetName = Literal["generic", "okta", "entra"]


class ScimEndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    preset: PresetName = "generic"


class ScimEndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID
    name: str
    preset: str
    enabled: bool
    last_sync_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class ScimEndpointCreated(ScimEndpointOut):
    """Returned exactly once. Carries the plaintext bearer token."""

    token: str = Field(description="Bearer token. Shown once at creation.")


class ScimGroupRoleMap(BaseModel):
    """Map a SCIM group's ``display_name`` to a system role within the org."""

    display_name: str = Field(min_length=1, max_length=255)
    role_name: Literal["owner", "admin", "member", "viewer", "service"]


class ScimGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    display_name: str
    external_id: str | None
    role_name: str | None
