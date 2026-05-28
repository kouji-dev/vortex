"""Pydantic schemas for the GDPR API."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel

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
