"""Pydantic schemas for LDAP/AD connection admin + login."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LdapConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="ldap", pattern="^(ldap|active_directory)$")
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    bind_dn: str = Field(min_length=1, max_length=512)
    bind_secret: str = Field(min_length=1, max_length=1024)
    base_dn: str = Field(min_length=1, max_length=512)
    user_filter: str | None = Field(default=None, max_length=512)
    group_filter: str | None = Field(default=None, max_length=512)
    tls_mode: str = Field(default="none", pattern="^(none|starttls|ldaps)$")
    attr_map: dict[str, str] | None = None
    group_role_map: dict[str, str] | None = None
    enabled: bool = True


class LdapConnectionPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    bind_dn: str | None = Field(default=None, max_length=512)
    bind_secret: str | None = Field(default=None, max_length=1024)
    base_dn: str | None = Field(default=None, max_length=512)
    user_filter: str | None = Field(default=None, max_length=512)
    group_filter: str | None = Field(default=None, max_length=512)
    tls_mode: str | None = Field(default=None, pattern="^(none|starttls|ldaps)$")
    attr_map: dict[str, str] | None = None
    group_role_map: dict[str, str] | None = None
    enabled: bool | None = None


class LdapConnectionOut(BaseModel):
    """Public shape — the bind secret is never returned."""

    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID | None
    name: str
    kind: str
    host: str
    port: int
    bind_dn: str
    base_dn: str
    user_filter: str
    group_filter: str | None
    tls_mode: str
    attr_map: dict[str, str] | None = Field(default=None, alias="attr_map_json")
    group_role_map: dict[str, str] | None = Field(
        default=None, alias="group_role_map_json"
    )
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LdapTestResult(BaseModel):
    ok: bool
    message: str | None = None


class LdapLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)
    connection_id: _uuid.UUID | None = None
    org_slug: str | None = None
