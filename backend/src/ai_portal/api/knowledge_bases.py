from __future__ import annotations

import asyncio
import logging
import uuid
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

    model_config = {"from_attributes": True}


class KnowledgeBasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    status: str
    created_at: object

    model_config = {"from_attributes": True}


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
) -> list[KnowledgeBase]:
    return list(
        db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_user_id == user.id)
            .order_by(KnowledgeBase.id.desc())
        ).all()
    )


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


@router.post("/{knowledge_base_id}/documents", status_code=status.HTTP_200_OK)
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int | str]:
    kb = _get_owned_kb(db, user, knowledge_base_id)
    settings = get_settings()

    safe_name = Path(file.filename or "upload").name
    dest_dir = Path(settings.upload_dir) / "kb" / str(kb.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = dest_dir / dest_name

    content = await file.read()
    max_bytes = settings.kb_max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.kb_max_file_size_mb} MB.",
        )
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
        return {
            "document_id": doc.id,
            "status": doc.status,
            "ingest_error": embedding_svc.embeddings_missing_key_message(),
        }

    try:
        ingest_err = await asyncio.to_thread(ingest_document, doc.id)
    except Exception as e:
        logger.exception("ingest_failed", extra={"document_id": doc.id})
        doc.status = "failed"
        db.commit()
        db.refresh(doc)
        return {"document_id": doc.id, "status": doc.status, "ingest_error": str(e)}

    db.refresh(doc)
    out: dict[str, int | str] = {"document_id": doc.id, "status": doc.status}
    if ingest_err:
        out["ingest_error"] = ingest_err
    return out


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
    }
