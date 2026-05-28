"""Document version retention policy.

For every ``KbDocument``, keep the most-recent ``keep_n`` versions and delete
older ones. ``keep_n`` is configurable per call (default 10). Per-KB override
read from ``KnowledgeBase.settings_json['version_retention']`` when present.

Wired into the scheduler to run daily; also exposed as a direct callable for
admins ("Clean up versions now" button).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KbDocument, KbDocumentVersion, KnowledgeBase

logger = logging.getLogger(__name__)

DEFAULT_KEEP = 10
SETTINGS_KEY = "version_retention"


@dataclass(frozen=True)
class CleanupReport:
    """Per-run summary: how much was reclaimed."""

    kbs_processed: int
    documents_processed: int
    versions_deleted: int


def _resolve_keep(kb: KnowledgeBase | None, default: int) -> int:
    if kb is None:
        return default
    raw = (kb.settings_json or {}).get(SETTINGS_KEY)
    if isinstance(raw, int) and raw > 0:
        return raw
    return default


def cleanup_versions_for_document(
    db: Session,
    *,
    document_id,
    keep_n: int,
) -> int:
    """Delete versions older than the ``keep_n`` newest. Returns deleted count."""
    versions = list(
        db.scalars(
            select(KbDocumentVersion)
            .where(KbDocumentVersion.document_id == document_id)
            .order_by(KbDocumentVersion.version_no.desc())
        )
    )
    if len(versions) <= keep_n:
        return 0
    to_delete = versions[keep_n:]
    for v in to_delete:
        db.delete(v)
    return len(to_delete)


def cleanup_versions_for_kb(
    db: Session,
    *,
    kb_id: int,
    keep_n: int | None = None,
) -> CleanupReport:
    """Clean every doc in ``kb_id``."""
    kb = db.get(KnowledgeBase, kb_id)
    resolved = keep_n if keep_n is not None else _resolve_keep(kb, DEFAULT_KEEP)
    docs = list(
        db.scalars(select(KbDocument).where(KbDocument.kb_id == kb_id))
    )
    total_deleted = 0
    for d in docs:
        total_deleted += cleanup_versions_for_document(
            db, document_id=d.id, keep_n=resolved
        )
    if total_deleted:
        db.commit()
    return CleanupReport(
        kbs_processed=1,
        documents_processed=len(docs),
        versions_deleted=total_deleted,
    )


def cleanup_versions_global(
    db: Session,
    *,
    default_keep: int = DEFAULT_KEEP,
) -> CleanupReport:
    """Run cleanup across every KB. Returns aggregate counts."""
    kbs = list(db.scalars(select(KnowledgeBase)))
    docs_total = 0
    deleted_total = 0
    for kb in kbs:
        keep = _resolve_keep(kb, default_keep)
        docs = list(
            db.scalars(select(KbDocument).where(KbDocument.kb_id == kb.id))
        )
        docs_total += len(docs)
        for d in docs:
            deleted_total += cleanup_versions_for_document(
                db, document_id=d.id, keep_n=keep
            )
    if deleted_total:
        db.commit()
    logger.info(
        "version_cleanup global: kbs=%d docs=%d deleted=%d",
        len(kbs), docs_total, deleted_total,
    )
    return CleanupReport(
        kbs_processed=len(kbs),
        documents_processed=docs_total,
        versions_deleted=deleted_total,
    )


__all__ = [
    "CleanupReport",
    "DEFAULT_KEEP",
    "cleanup_versions_for_document",
    "cleanup_versions_for_kb",
    "cleanup_versions_global",
]
