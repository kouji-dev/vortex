from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ai_portal.api.assistants import _can_access_assistant
from ai_portal.api.deps import get_current_user, get_db
from ai_portal.config import get_settings
from ai_portal.models import Assistant, Document, User
from ai_portal.tasks.ingest import ingest_document

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


@router.post(
    "/api/assistants/{assistant_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    assistant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int | str]:
    settings = get_settings()
    assistant = db.get(Assistant, assistant_id)
    if assistant is None or not _can_access_assistant(db, user, assistant):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")

    safe_name = Path(file.filename or "upload").name
    dest_dir = Path(settings.upload_dir) / str(assistant_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = dest_dir / dest_name

    content = await file.read()
    dest_path.write_bytes(content)

    doc = Document(
        assistant_id=assistant_id,
        filename=safe_name,
        storage_path=str(dest_path.resolve()),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        ingest_document.delay(doc.id)
    except Exception as e:
        logger.exception("enqueue_ingest_failed")
        doc.status = "failed"
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Celery unavailable: {e}",
        ) from e

    return {"document_id": doc.id, "status": doc.status}
