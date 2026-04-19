"""Pydantic schemas for RBAC policy API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RbacPolicyResponse(BaseModel):
    id: int
    org_id: UUID
    model_allowlist: list[str] | None
    model_role_bindings: dict
    capability_role_bindings: dict
    tool_role_bindings: dict
    default_policy: str
    updated_at: datetime

    class Config:
        from_attributes = True


class RbacPolicyUpdate(BaseModel):
    model_allowlist: list[str] | None = None
    model_role_bindings: dict = {}
    capability_role_bindings: dict = {}
    tool_role_bindings: dict = {}
    default_policy: str = "allow"
