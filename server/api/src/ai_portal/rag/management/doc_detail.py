"""Document-detail serializer for the management surface.

Joins a ``KbDocument`` row with the most recent ``KbSyncError`` matching its
``source_uri`` so the quarantine page can show *why* ingestion failed and
*which* sync run produced the error.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DocDetailRow:
    """Container that maps cleanly into a Pydantic out model."""

    id: _uuid.UUID
    kb_id: int
    source_uri: str
    title: str
    status: str
    quarantine_reason: str | None
    last_error: str | None
    sync_run_id: _uuid.UUID | None
    last_error_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class DocDetailOut(BaseModel):
    id: str
    kb_id: int
    source_uri: str
    title: str
    status: str
    quarantine_reason: str | None = None
    last_error: str | None = None
    sync_run_id: str | None = None
    last_error_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def serialize_doc_detail(doc: Any, last_err: Any | None) -> DocDetailRow:
    """Pure: stitch a KbDocument + (optional) KbSyncError into a row.

    ``doc`` and ``last_err`` are SQLAlchemy rows OR stand-ins exposing the
    same attribute names.
    """
    err_text = None
    run_id = None
    err_at = None
    if last_err is not None:
        err_text = getattr(last_err, "error", None)
        run_id = getattr(last_err, "run_id", None)
        err_at = getattr(last_err, "created_at", None)
    return DocDetailRow(
        id=getattr(doc, "id"),
        kb_id=int(getattr(doc, "kb_id")),
        source_uri=getattr(doc, "source_uri", "") or "",
        title=getattr(doc, "title", "") or "",
        status=getattr(doc, "status", "") or "",
        quarantine_reason=getattr(doc, "quarantine_reason", None),
        last_error=err_text,
        sync_run_id=run_id,
        last_error_at=err_at,
        created_at=getattr(doc, "created_at", None),
        updated_at=getattr(doc, "updated_at", None),
    )


def to_out(row: DocDetailRow) -> DocDetailOut:
    return DocDetailOut(
        id=str(row.id),
        kb_id=row.kb_id,
        source_uri=row.source_uri,
        title=row.title,
        status=row.status,
        quarantine_reason=row.quarantine_reason,
        last_error=row.last_error,
        sync_run_id=str(row.sync_run_id) if row.sync_run_id else None,
        last_error_at=row.last_error_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def fetch_doc_detail(
    db: Session, *, kb_id: int, doc_id: _uuid.UUID
) -> DocDetailOut | None:
    """DB-backed: load a kb_document + its latest matching sync error."""
    from ai_portal.knowledge_base.model import KbDocument
    from ai_portal.rag.connectors.model import KbSyncError

    doc = db.scalar(
        select(KbDocument).where(
            KbDocument.id == doc_id, KbDocument.kb_id == kb_id
        )
    )
    if doc is None:
        return None
    last_err = db.scalar(
        select(KbSyncError)
        .where(KbSyncError.source_uri == doc.source_uri)
        .order_by(KbSyncError.created_at.desc())
        .limit(1)
    )
    return to_out(serialize_doc_detail(doc, last_err))


__all__ = [
    "DocDetailOut",
    "DocDetailRow",
    "fetch_doc_detail",
    "serialize_doc_detail",
    "to_out",
]
