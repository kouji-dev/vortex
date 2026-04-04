from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_user, get_db
from ai_portal.config import get_settings
from ai_portal.models import (
    ConnectorSyncJob,
    Document,
    KnowledgeBase,
    KnowledgeBaseConnector,
    User,
)
from ai_portal.models.connector import CONNECTOR_KINDS
from ai_portal.services import embedding as embedding_svc
from ai_portal.services.ingest_queue import enqueue_document_ingest, ingest_uses_queue
from ai_portal.tasks.connector_jobs import run_connector_sync_job
from ai_portal.tasks.ingest import ingest_document

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])
logger = logging.getLogger(__name__)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)


class KnowledgeBaseRead(BaseModel):
    id: int
    name: str
    description: str
    owner_user_id: int
    created_at: object
    document_count: int | None = None
    chunks_count: int | None = None
    size_bytes: int | None = None

    model_config = {"from_attributes": True}


class KnowledgeBasePage(BaseModel):
    items: list[KnowledgeBaseRead]
    next_cursor: int | None = None


class KnowledgeBasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    status: str
    ingest_error: str | None = None
    created_at: object

    model_config = {"from_attributes": True}


class DocumentUploadResultRead(BaseModel):
    """``document_id`` is set when a row was persisted; omitted when the file was rejected (e.g. too large)."""

    document_id: int | None = None
    status: str
    filename: str
    ingest_error: str | None = None


class DocumentsUploadResponseRead(BaseModel):
    results: list[DocumentUploadResultRead]


ConnectorKind = Literal["files", "github", "gitlab", "confluence", "s3"]


class KnowledgeBaseConnectorCreate(BaseModel):
    kind: ConnectorKind
    label: str = Field(default="", max_length=255)
    settings: dict = Field(default_factory=dict)


class KnowledgeBaseConnectorPatch(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    settings: dict | None = None
    enabled: bool | None = None


class KnowledgeBaseConnectorRead(BaseModel):
    id: int
    knowledge_base_id: int
    kind: str
    label: str
    settings: dict
    enabled: bool
    created_at: object

    model_config = {"from_attributes": True}


class ConnectorSyncJobRead(BaseModel):
    id: int
    knowledge_base_id: int
    connector_id: int
    job_type: str
    status: str
    error_message: str | None
    meta: dict
    created_at: object
    started_at: object | None
    finished_at: object | None

    model_config = {"from_attributes": True}


def _get_owned_kb(db: Session, user: User, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return kb


def _get_owned_connector(
    db: Session, user: User, kb_id: int, connector_id: int
) -> KnowledgeBaseConnector:
    _get_owned_kb(db, user, kb_id)
    c = db.get(KnowledgeBaseConnector, connector_id)
    if c is None or c.knowledge_base_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return c


def _schedule_document_ingest(document_id: int, background_tasks: BackgroundTasks) -> None:
    """Run ingest asynchronously: RQ worker when Redis is configured, else FastAPI background task."""
    settings = get_settings()
    if ingest_uses_queue(settings):
        try:
            enqueue_document_ingest(document_id, settings=settings)
            return
        except Exception:
            logger.exception(
                "ingest_enqueue_failed_falling_back_to_background",
                extra={"document_id": document_id},
            )
    background_tasks.add_task(ingest_document, document_id)


async def _store_and_queue_kb_upload(
    kb: KnowledgeBase,
    upload: UploadFile,
    db: Session,
    settings,
    background_tasks: BackgroundTasks,
) -> DocumentUploadResultRead:
    safe_name = Path(upload.filename or "upload").name
    content = await upload.read()
    max_bytes = settings.kb_max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        return DocumentUploadResultRead(
            status="failed",
            filename=safe_name,
            ingest_error=(
                f"File too large. Maximum size is {settings.kb_max_file_size_mb} MB."
            ),
        )

    dest_dir = Path(settings.upload_dir) / "kb" / str(kb.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = dest_dir / dest_name
    dest_path.write_bytes(content)

    doc = Document(
        knowledge_base_id=kb.id,
        filename=safe_name,
        storage_path=str(dest_path.resolve()),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if not embedding_svc.embeddings_configured(settings):
        doc.status = "failed"
        db.commit()
        db.refresh(doc)
        return DocumentUploadResultRead(
            document_id=doc.id,
            status=doc.status,
            filename=safe_name,
            ingest_error=embedding_svc.embeddings_missing_key_message(),
        )

    _schedule_document_ingest(doc.id, background_tasks)
    db.refresh(doc)
    return DocumentUploadResultRead(
        document_id=doc.id,
        status=doc.status,
        filename=safe_name,
    )


def _build_kb_rows(db: Session, kbs: list[KnowledgeBase]) -> list[KnowledgeBaseRead]:
    if not kbs:
        return []

    kb_ids = [kb.id for kb in kbs]
    docs = list(
        db.scalars(select(Document).where(Document.knowledge_base_id.in_(kb_ids))).all()
    )

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


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    body: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBase:
    kb = KnowledgeBase(
        name=body.name.strip(),
        description=(body.description or "").strip(),
        owner_user_id=user.id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[KnowledgeBaseRead]:
    kbs = list(
        db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_user_id == user.id)
            .order_by(KnowledgeBase.id.desc())
        ).all()
    )
    return _build_kb_rows(db, kbs)


@router.get("/page", response_model=KnowledgeBasePage)
def list_knowledge_bases_page(
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBasePage:
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.owner_user_id == user.id)
        .order_by(KnowledgeBase.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(KnowledgeBase.id < cursor)
    rows = list(db.scalars(stmt).all())
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = _build_kb_rows(db, page_rows)
    next_cursor = page_rows[-1].id if has_more and page_rows else None
    return KnowledgeBasePage(items=items, next_cursor=next_cursor)


@router.get(
    "/{knowledge_base_id}/connector-jobs",
    response_model=list[ConnectorSyncJobRead],
)
def list_connector_jobs(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConnectorSyncJob]:
    _get_owned_kb(db, user, knowledge_base_id)
    return list(
        db.scalars(
            select(ConnectorSyncJob)
            .where(ConnectorSyncJob.knowledge_base_id == knowledge_base_id)
            .order_by(ConnectorSyncJob.id.desc())
            .limit(limit)
        ).all()
    )


@router.get(
    "/{knowledge_base_id}/connectors",
    response_model=list[KnowledgeBaseConnectorRead],
)
def list_connectors(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[KnowledgeBaseConnector]:
    _get_owned_kb(db, user, knowledge_base_id)
    return list(
        db.scalars(
            select(KnowledgeBaseConnector)
            .where(KnowledgeBaseConnector.knowledge_base_id == knowledge_base_id)
            .order_by(KnowledgeBaseConnector.id.asc())
        ).all()
    )


@router.post(
    "/{knowledge_base_id}/connectors",
    response_model=KnowledgeBaseConnectorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_connector(
    knowledge_base_id: int,
    body: KnowledgeBaseConnectorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBaseConnector:
    _get_owned_kb(db, user, knowledge_base_id)
    if body.kind not in CONNECTOR_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector kind",
        )
    c = KnowledgeBaseConnector(
        knowledge_base_id=knowledge_base_id,
        kind=body.kind,
        label=(body.label or "").strip(),
        settings=body.settings or {},
        enabled=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.patch(
    "/{knowledge_base_id}/connectors/{connector_id}",
    response_model=KnowledgeBaseConnectorRead,
)
def patch_connector(
    knowledge_base_id: int,
    connector_id: int,
    body: KnowledgeBaseConnectorPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBaseConnector:
    c = _get_owned_connector(db, user, knowledge_base_id, connector_id)
    if body.label is not None:
        c.label = body.label.strip()
    if body.settings is not None:
        c.settings = body.settings
    if body.enabled is not None:
        c.enabled = body.enabled
    db.commit()
    db.refresh(c)
    return c


@router.delete(
    "/{knowledge_base_id}/connectors/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_connector(
    knowledge_base_id: int,
    connector_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    c = _get_owned_connector(db, user, knowledge_base_id, connector_id)
    db.delete(c)
    db.commit()


@router.post(
    "/{knowledge_base_id}/connectors/{connector_id}/sync",
    response_model=ConnectorSyncJobRead,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_connector_sync(
    knowledge_base_id: int,
    connector_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConnectorSyncJob:
    c = _get_owned_connector(db, user, knowledge_base_id, connector_id)
    if not c.enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Connector is disabled",
        )
    job = ConnectorSyncJob(
        knowledge_base_id=knowledge_base_id,
        connector_id=connector_id,
        job_type="full_sync",
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_connector_sync_job, job.id)
    return job


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBase:
    return _get_owned_kb(db, user, knowledge_base_id)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def patch_knowledge_base(
    knowledge_base_id: int,
    body: KnowledgeBasePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBase:
    kb = _get_owned_kb(db, user, knowledge_base_id)
    if body.name is not None:
        kb.name = body.name.strip()
    if body.description is not None:
        kb.description = body.description.strip()
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
def list_documents(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Document]:
    _get_owned_kb(db, user, knowledge_base_id)
    return list(
        db.scalars(
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.id.desc())
        ).all()
    )


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    knowledge_base_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    _get_owned_kb(db, user, knowledge_base_id)
    doc = db.get(Document, document_id)
    if doc is None or doc.knowledge_base_id != knowledge_base_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    db.delete(doc)
    db.commit()


@router.post(
    "/{knowledge_base_id}/documents",
    status_code=status.HTTP_200_OK,
    response_model=DocumentsUploadResponseRead,
)
async def upload_document(
    knowledge_base_id: int,
    file: list[UploadFile] = File(
        ...,
        description="One or more files (repeat the `file` field for each part).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> DocumentsUploadResponseRead:
    """Persist uploads and queue ingest. Response returns immediately with ``pending``; worker sets ``ingesting`` then ``ready``/``failed``."""
    kb = _get_owned_kb(db, user, knowledge_base_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one file is required.",
        )
    settings = get_settings()
    results: list[DocumentUploadResultRead] = []
    for part in file:
        results.append(
            await _store_and_queue_kb_upload(kb, part, db, settings, background_tasks)
        )
    return DocumentsUploadResponseRead(results=results)


@router.get("/{kb_id}/documents/{doc_id}/progress")
def get_document_progress(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """Return ingest progress for a document."""
    doc = db.scalars(
        select(Document).where(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id,
        )
    ).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": doc.id,
        "status": doc.status,
        "chunks_done": doc.chunks_done,
        "chunks_total": doc.chunks_total,
        "ingest_error": doc.ingest_error,
    }
