"""Files service — bytes in BlobStore, metadata in ``gateway_files``.

The service is the only place that knows about the blob key layout. The
router and tests use :class:`FilesService` to upload, presign, and delete.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.control_plane import BlobStore
from ai_portal.gateway.files.model import GatewayFile


class FileNotFound(KeyError):
    """Raised when an id is not found for the caller's org."""


@dataclass(frozen=True)
class FileMetadata:
    """Metadata returned to API callers (no bytes)."""

    id: _uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    purpose: str
    blob_key: str


class FilesService:
    """Bytes -> BlobStore, metadata -> ``gateway_files``."""

    def __init__(self, *, db: Session, blob_store: BlobStore) -> None:
        self.db = db
        self.blob_store = blob_store

    # ── public ──────────────────────────────────────────────────────────

    async def upload(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int | None,
        data: bytes,
        filename: str,
        content_type: str,
        purpose: str = "user_data",
    ) -> FileMetadata:
        """Store ``data`` in the blob store; insert metadata row."""
        file_id = _uuid.uuid4()
        key = self._blob_key(org_id=org_id, file_id=file_id, filename=filename)
        await self.blob_store.put(key, data, content_type)

        row = GatewayFile(
            id=file_id,
            org_id=org_id,
            actor_user_id=actor_user_id,
            blob_key=key,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            purpose=purpose,
        )
        self.db.add(row)
        self.db.flush()
        self.db.commit()
        return self._to_metadata(row)

    def get(self, *, org_id: _uuid.UUID, file_id: _uuid.UUID) -> FileMetadata:
        row = self._fetch(org_id=org_id, file_id=file_id)
        return self._to_metadata(row)

    async def presign_get(
        self,
        *,
        org_id: _uuid.UUID,
        file_id: _uuid.UUID,
        expires_in: int = 300,
    ) -> str:
        row = self._fetch(org_id=org_id, file_id=file_id)
        return await self.blob_store.presign_get(row.blob_key, expires_in)

    async def delete(
        self, *, org_id: _uuid.UUID, file_id: _uuid.UUID
    ) -> None:
        row = self._fetch(org_id=org_id, file_id=file_id)
        await self.blob_store.delete(row.blob_key)
        self.db.delete(row)
        self.db.commit()

    # ── helpers ─────────────────────────────────────────────────────────

    def _fetch(
        self, *, org_id: _uuid.UUID, file_id: _uuid.UUID
    ) -> GatewayFile:
        row = self.db.scalar(
            select(GatewayFile).where(
                GatewayFile.id == file_id,
                GatewayFile.org_id == org_id,
            )
        )
        if row is None:
            raise FileNotFound(str(file_id))
        return row

    @staticmethod
    def _blob_key(
        *, org_id: _uuid.UUID, file_id: _uuid.UUID, filename: str
    ) -> str:
        # Path-like key: gateway/files/<org>/<id>/<filename>
        # Sanitise filename — strip any path separators, keep extension.
        safe = filename.replace("/", "_").replace("\\", "_") or "blob"
        return f"gateway/files/{org_id}/{file_id}/{safe}"

    @staticmethod
    def _to_metadata(row: GatewayFile) -> FileMetadata:
        return FileMetadata(
            id=row.id,
            filename=row.filename,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            purpose=row.purpose,
            blob_key=row.blob_key,
        )


__all__ = ["FileMetadata", "FileNotFound", "FilesService"]
