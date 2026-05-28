"""Phase A: KB management operations (archive, clone, visibility filter).

Thin service helpers on top of ``knowledge_base.repository``. Designed to
be called from the existing router. Multi-service domain split keeps each
file SRP-aligned.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import (
    Document,
    KbStatus,
    KbVisibility,
    KnowledgeBase,
    KnowledgeBaseConnector,
)


@dataclass(frozen=True)
class VisibilityFilter:
    """Honor visibility when listing KBs for an actor."""

    user_id: int
    org_id: object
    team_ids: tuple[str, ...] = ()

    def applies_to(self, kb: KnowledgeBase) -> bool:
        if kb.visibility == KbVisibility.private.value:
            return kb.owner_user_id == self.user_id
        if kb.visibility == KbVisibility.team.value:
            # Team membership opaque to this module — caller injects ``team_ids``
            # if the KB is gated by a team token in ``settings_json["team_id"]``.
            team_id = (kb.settings_json or {}).get("team_id")
            if team_id is None:
                return True
            return str(team_id) in self.team_ids
        if kb.visibility == KbVisibility.org_public.value:
            return kb.org_id == self.org_id
        # Unknown visibility → conservative: hide.
        return False


def archive_kb(db: Session, kb: KnowledgeBase) -> KnowledgeBase:
    kb.status = KbStatus.archived.value
    db.commit()
    db.refresh(kb)
    return kb


def unarchive_kb(db: Session, kb: KnowledgeBase) -> KnowledgeBase:
    kb.status = KbStatus.active.value
    db.commit()
    db.refresh(kb)
    return kb


def soft_delete_kb(db: Session, kb: KnowledgeBase) -> KnowledgeBase:
    kb.status = KbStatus.deleted.value
    db.commit()
    db.refresh(kb)
    return kb


def clone_kb(
    db: Session,
    src: KnowledgeBase,
    *,
    new_name: str,
    new_slug: str | None = None,
    copy_connectors: bool = True,
) -> KnowledgeBase:
    """Clone KB settings + connectors. Documents are NOT copied."""
    dst = KnowledgeBase(
        org_id=src.org_id,
        name=new_name,
        description=src.description,
        owner_user_id=src.owner_user_id,
        visibility=src.visibility,
        embedder_id=src.embedder_id,
        vector_backend=src.vector_backend,
        chunker_id=src.chunker_id,
        settings_json=dict(src.settings_json or {}),
        status=KbStatus.active.value,
        slug=new_slug,
        tags=list(src.tags or []),
        default_retrieval_policy_id=src.default_retrieval_policy_id,
        language=src.language,
    )
    db.add(dst)
    db.flush()  # need dst.id for connector copies
    if copy_connectors:
        connectors = list(
            db.scalars(
                select(KnowledgeBaseConnector).where(
                    KnowledgeBaseConnector.knowledge_base_id == src.id
                )
            ).all()
        )
        for c in connectors:
            db.add(
                KnowledgeBaseConnector(
                    knowledge_base_id=dst.id,
                    kind=c.kind,
                    label=c.label,
                    settings=dict(c.settings or {}),
                    enabled=c.enabled,
                )
            )
    db.commit()
    db.refresh(dst)
    return dst


def copy_documents(db: Session, *, src_kb_id: int, dst_kb_id: int) -> int:
    """Copy Document rows from one KB to another. Returns count.

    Copies the metadata row only — re-ingest is the worker's job.
    Chunks/embeddings are NOT copied (rebuild via ingest).
    """
    docs = list(
        db.scalars(
            select(Document).where(Document.knowledge_base_id == src_kb_id)
        )
    )
    n = 0
    for d in docs:
        db.add(
            Document(
                knowledge_base_id=dst_kb_id,
                filename=d.filename,
                storage_path=d.storage_path,
                status="pending",
            )
        )
        n += 1
    if n:
        db.commit()
    return n
