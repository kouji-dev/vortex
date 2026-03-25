from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_user, get_db
from ai_portal.config import get_settings
from ai_portal.models import Document, KnowledgeBase, User
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


def _get_owned_kb(db: Session, user: User, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return kb


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

    try:
        await asyncio.to_thread(ingest_document, doc.id)
    except Exception as e:
        logger.exception("ingest_failed", extra={"document_id": doc.id})
        doc.status = "failed"
        db.commit()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingest failed: {e}",
        ) from e

    db.refresh(doc)
    return {"document_id": doc.id, "status": doc.status}
