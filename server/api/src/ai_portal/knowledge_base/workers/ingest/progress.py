"""Helpers for updating Document ingest progress in the DB."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import Document


def set_chunks_total(db: Session, doc: Document, *, total: int) -> None:
    """Set the known total chunk count once the file has been scanned."""
    doc.chunks_total = total
    db.commit()


def update_progress(db: Session, doc: Document, *, chunks_done: int) -> None:
    """Update how many chunks have been committed so far."""
    doc.chunks_done = chunks_done
    db.commit()
