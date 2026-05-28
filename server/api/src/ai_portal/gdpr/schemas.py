"""Pydantic schemas for the GDPR API."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Export ──────────────────────────────────────────────────────────────────


class DataExportCreate(BaseModel):
    """POST /v1/data-export body.

    ``notify_recipient`` overrides the default (caller's email) on the
    presigned-URL email.
    """

    notify_recipient: str | None = None


class DataExportJobOut(BaseModel):
    id: _uuid.UUID
    org_id: _uuid.UUID
    requested_by: int | None
    status: str
    result_url: str | None
    requested_at: datetime
    completed_at: datetime | None


# ── Delete ──────────────────────────────────────────────────────────────────


class DataDeleteCreate(BaseModel):
    """POST /v1/data-delete body.

    ``scope`` selects what to delete. Two supported shapes:

    - ``{"subject": "org"}``  — wipe entire org (org_id derived from actor)
    - ``{"subject": "user", "user_id": <int>}`` — wipe one user's rows only
    """

    scope: dict[str, Any] = Field(default_factory=lambda: {"subject": "org"})


class DataDeleteJobOut(BaseModel):
    id: _uuid.UUID
    org_id: _uuid.UUID
    scope_json: dict[str, Any]
    status: str
    requested_at: datetime
    completed_at: datetime | None
