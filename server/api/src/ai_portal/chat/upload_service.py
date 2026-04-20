"""Chat upload service — stores per-message file attachments."""

from __future__ import annotations

import uuid as _uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ai_portal.auth.model import User
from ai_portal.chat.model import ChatUpload
from ai_portal.chat.schemas import ChatUploadRead


async def create_upload(
    *,
    db: Session,
    user: User,
    org_id: _uuid.UUID,
    thread_id: int,
    file: UploadFile,
    upload_dir: str,
) -> ChatUploadRead:
    content = await file.read()
    size_bytes = len(content)

    dest_dir = Path(upload_dir) / "chat"
    dest_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{_uuid.uuid4().hex}_{Path(file.filename or 'upload').name}"
    stored_path = dest_dir / stored_name
    stored_path.write_bytes(content)

    record = ChatUpload(
        org_id=org_id,
        user_id=user.id,
        thread_id=thread_id,
        original_filename=file.filename or "upload",
        stored_path=str(stored_path),
        size_bytes=size_bytes,
        content_type=file.content_type,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ChatUploadRead.model_validate(record)


def load_upload_text(record: ChatUpload) -> str | None:
    """Return the text content of an upload, or None if unreadable."""
    try:
        return Path(record.stored_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def get_uploads_by_ids(db: Session, ids: list[int], user_id: int) -> list[ChatUpload]:
    if not ids:
        return []
    from sqlalchemy import select
    rows = db.scalars(
        select(ChatUpload).where(
            ChatUpload.id.in_(ids),
            ChatUpload.user_id == user_id,
        )
    ).all()
    return list(rows)
