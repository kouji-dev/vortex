from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import (
    ConnectorSyncJob,
    Document,
    KnowledgeBase,
    KnowledgeBaseConnector,
)


def get_kb_by_id(db: Session, kb_id: int) -> KnowledgeBase | None:
    return db.get(KnowledgeBase, kb_id)


def list_kbs_by_user(db: Session, user_id: int, org_id) -> list[KnowledgeBase]:
    return list(
        db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_user_id == user_id)
            .where(KnowledgeBase.org_id == org_id)
            .order_by(KnowledgeBase.id.desc())
        ).all()
    )


def list_kbs_by_user_page(
    db: Session,
    user_id: int,
    org_id,
    limit: int,
    cursor: int | None,
) -> list[KnowledgeBase]:
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.owner_user_id == user_id)
        .where(KnowledgeBase.org_id == org_id)
        .order_by(KnowledgeBase.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(KnowledgeBase.id < cursor)
    return list(db.scalars(stmt).all())


def create_kb(db: Session, name: str, description: str, owner_user_id: int, org_id) -> KnowledgeBase:
    kb = KnowledgeBase(
        name=name,
        description=description,
        owner_user_id=owner_user_id,
        org_id=org_id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def update_kb(db: Session, kb: KnowledgeBase, name: str | None, description: str | None) -> KnowledgeBase:
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    db.commit()
    db.refresh(kb)
    return kb


def delete_kb(db: Session, kb: KnowledgeBase) -> None:
    db.delete(kb)
    db.commit()


def get_connector_by_id(db: Session, connector_id: int) -> KnowledgeBaseConnector | None:
    return db.get(KnowledgeBaseConnector, connector_id)


def list_connectors_for_kb(db: Session, kb_id: int) -> list[KnowledgeBaseConnector]:
    return list(
        db.scalars(
            select(KnowledgeBaseConnector)
            .where(KnowledgeBaseConnector.knowledge_base_id == kb_id)
            .order_by(KnowledgeBaseConnector.id.asc())
        ).all()
    )


def create_connector(
    db: Session,
    kb_id: int,
    kind: str,
    label: str,
    settings: dict,
) -> KnowledgeBaseConnector:
    c = KnowledgeBaseConnector(
        knowledge_base_id=kb_id,
        kind=kind,
        label=label,
        settings=settings,
        enabled=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_connector(
    db: Session,
    c: KnowledgeBaseConnector,
    label: str | None,
    settings: dict | None,
    enabled: bool | None,
) -> KnowledgeBaseConnector:
    if label is not None:
        c.label = label
    if settings is not None:
        c.settings = settings
    if enabled is not None:
        c.enabled = enabled
    db.commit()
    db.refresh(c)
    return c


def delete_connector(db: Session, c: KnowledgeBaseConnector) -> None:
    db.delete(c)
    db.commit()


def list_connector_jobs(db: Session, kb_id: int, limit: int) -> list[ConnectorSyncJob]:
    return list(
        db.scalars(
            select(ConnectorSyncJob)
            .where(ConnectorSyncJob.knowledge_base_id == kb_id)
            .order_by(ConnectorSyncJob.id.desc())
            .limit(limit)
        ).all()
    )


def create_connector_sync_job(
    db: Session,
    kb_id: int,
    connector_id: int,
) -> ConnectorSyncJob:
    job = ConnectorSyncJob(
        knowledge_base_id=kb_id,
        connector_id=connector_id,
        job_type="full_sync",
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_documents_for_kb(db: Session, kb_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.knowledge_base_id == kb_id)
            .order_by(Document.id.desc())
        ).all()
    )


def list_documents_for_kbs(db: Session, kb_ids: list[int]) -> list[Document]:
    return list(
        db.scalars(select(Document).where(Document.knowledge_base_id.in_(kb_ids))).all()
    )


def get_document_by_id(db: Session, document_id: int) -> Document | None:
    return db.get(Document, document_id)


def get_document_in_kb(db: Session, doc_id: int, kb_id: int) -> Document | None:
    return db.scalars(
        select(Document).where(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
    ).first()


def create_document(
    db: Session,
    kb_id: int,
    filename: str,
    storage_path: str,
) -> Document:
    doc = Document(
        knowledge_base_id=kb_id,
        filename=filename,
        storage_path=storage_path,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def update_document_status(db: Session, doc: Document, status: str, ingest_error: str | None = None) -> Document:
    doc.status = status
    if ingest_error is not None:
        doc.ingest_error = ingest_error
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, doc: Document) -> None:
    db.delete(doc)
    db.commit()


def build_kb_stats(
    docs: list[Document],
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    """Return (document_counts, chunks_counts, size_totals) keyed by kb_id."""
    document_counts: dict[int, int] = defaultdict(int)
    chunks_counts: dict[int, int] = defaultdict(int)
    size_totals: dict[int, int] = defaultdict(int)

    for doc in docs:
        kb_id = doc.knowledge_base_id
        document_counts[kb_id] += 1
        chunks_counts[kb_id] += doc.chunks_total or 0
        try:
            size_totals[kb_id] += Path(doc.storage_path).stat().st_size
        except OSError:
            continue

    return document_counts, chunks_counts, size_totals
