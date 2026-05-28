"""OpenAI/Anthropic-compatible ``/v1/files`` surface.

Routes:

- ``POST   /v1/files``        — multipart upload; returns metadata
- ``GET    /v1/files``        — list metadata for the caller's org
- ``GET    /v1/files/{id}``   — return metadata + a short-lived presigned URL
- ``DELETE /v1/files/{id}``   — delete bytes + metadata row

The bytes live in the Control Plane :class:`BlobStore` (``local_fs`` for
dev/tests, S3/GCS/Azure in prod). Each file is org-scoped via RLS.
"""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_actor
from ai_portal.gateway.files.model import GatewayFile
from ai_portal.gateway.files.service import FileNotFound, FilesService
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1/files", tags=["gateway-files"])


def get_files_service(db: Session = Depends(get_db)) -> FilesService:
    """FastAPI dep — overrides install :class:`BlobStore` per-env.

    Default raises so production wiring + tests are forced to override.
    """
    raise RuntimeError(
        "no FilesService bound — override `get_files_service` in tests or "
        "wire it in app startup."
    )


def _serialize(row: GatewayFile, *, presigned_url: str | None = None) -> dict:
    out: dict[str, object] = {
        "id": str(row.id),
        "object": "file",
        "filename": row.filename,
        "purpose": row.purpose,
        "bytes": row.size_bytes,
        "content_type": row.content_type,
        "created_at": int(row.created_at.timestamp()),
    }
    if presigned_url is not None:
        out["url"] = presigned_url
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    purpose: str = Form("user_data"),
    actor: Actor = Depends(require_actor),
    svc: FilesService = Depends(get_files_service),
):
    """Multipart upload. Backed by Control Plane BlobStore."""
    data = await file.read()
    if not data:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="empty upload"
        )
    meta = await svc.upload(
        org_id=actor.org_id,
        actor_user_id=actor.user_id,
        data=data,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        purpose=purpose,
    )
    return {
        "id": str(meta.id),
        "object": "file",
        "filename": meta.filename,
        "purpose": meta.purpose,
        "bytes": meta.size_bytes,
        "content_type": meta.content_type,
    }


@router.get("")
def list_files(
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
):
    """List files for the caller's org."""
    rows = list(
        db.scalars(
            select(GatewayFile)
            .where(GatewayFile.org_id == actor.org_id)
            .order_by(GatewayFile.created_at.desc())
        )
    )
    return {"object": "list", "data": [_serialize(r) for r in rows]}


@router.get("/{file_id}")
async def get_file(
    file_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    db: Session = Depends(get_db),
    svc: FilesService = Depends(get_files_service),
):
    """Return metadata + a short-lived presigned download URL."""
    row = db.scalar(
        select(GatewayFile).where(
            GatewayFile.id == file_id,
            GatewayFile.org_id == actor.org_id,
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file not found")
    try:
        url = await svc.presign_get(
            org_id=actor.org_id, file_id=file_id, expires_in=300
        )
    except FileNotFound as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="file not found"
        ) from e
    return _serialize(row, presigned_url=url)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    actor: Actor = Depends(require_actor),
    svc: FilesService = Depends(get_files_service),
) -> None:
    try:
        await svc.delete(org_id=actor.org_id, file_id=file_id)
    except FileNotFound as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="file not found"
        ) from e


__all__ = ["get_files_service", "router"]
