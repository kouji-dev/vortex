from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.model import User
from ai_portal.knowledge_base.model import KnowledgeBase, KnowledgeBaseConnector
from ai_portal.knowledge_base import repository as repo
from ai_portal.knowledge_base.schemas import KnowledgeBaseRead

logger = logging.getLogger(__name__)


def get_owned_kb(db: Session, user: User, kb_id: int) -> KnowledgeBase:
    kb = repo.get_kb_by_id(db, kb_id)
    if kb is None or kb.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return kb


def get_owned_connector(
    db: Session, user: User, kb_id: int, connector_id: int
) -> KnowledgeBaseConnector:
    get_owned_kb(db, user, kb_id)
    c = repo.get_connector_by_id(db, connector_id)
    if c is None or c.knowledge_base_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return c


def build_kb_rows(db: Session, kbs: list[KnowledgeBase]) -> list[KnowledgeBaseRead]:
    if not kbs:
        return []

    kb_ids = [kb.id for kb in kbs]
    docs = repo.list_documents_for_kbs(db, kb_ids)
    document_counts, chunks_counts, size_totals = repo.build_kb_stats(docs)

    return [
        KnowledgeBaseRead(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            owner_user_id=kb.owner_user_id,
            created_at=kb.created_at,
            document_count=document_counts[kb.id],
            chunks_count=chunks_counts[kb.id],
            size_bytes=size_totals[kb.id],
        )
        for kb in kbs
    ]


from ai_portal.knowledge_base.ingest_service import (  # noqa: F401
    INGEST_JOB_FUNC,
    INGEST_QUEUE_NAME,
    enqueue_document_ingest,
    ingest_uses_queue,
    store_and_queue_kb_upload,
)
