"""File-upload connector.

Pulls documents from a Control-Plane BlobStore prefix. The REST upload
endpoint stores bytes at ``kb/{kb_id}/uploads/{filename}`` and this
connector enumerates that prefix on each sync.

No external auth required — BlobStore credentials are owned by the Control
Plane.

Delta strategy: per-object ETag. The orchestrator persists the highest
``modified_at`` seen across the run; subsequent runs request the prefix
again and skip objects whose ``cursor_token`` (== etag) matches the one
already stored on the document.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator

from ai_portal.rag.connectors import register
from ai_portal.rag.connectors.manifest import ConnectorManifest
from ai_portal.rag.connectors.protocol import (
    AclSet,
    FetchedDoc,
    SourceDoc,
)

_MANIFEST = ConnectorManifest(
    name="file_upload",
    auth_kinds=("none",),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["prefix"],
        "properties": {
            "prefix": {"type": "string"},
            "include_globs": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
)


class _NoopBlobLister:
    """Stand-in used when no blob_store is wired (e.g. unit tests)."""

    async def list(self, prefix: str):  # noqa: ARG002 - shape only
        return []


class FileUploadConnector:
    """Enumerates an in-portal BlobStore prefix."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], blob_store: Any) -> None:
        self._config = config
        self._blob_store = blob_store or _NoopBlobLister()
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "FileUploadConnector":
        # secret_store is expected to expose ``blob_store`` for this kind.
        blob_store = getattr(secret_store, "blob_store", None)
        return cls(config, blob_store)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        cursor_dt: datetime | None = None
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            except ValueError:
                cursor_dt = None
        prefix = self._config["prefix"]
        for entry in await self._blob_store.list(prefix):
            modified_at = entry.get("modified_at")
            if cursor_dt and modified_at and modified_at <= cursor_dt:
                continue
            etag = entry.get("etag")
            yield SourceDoc(
                source_uri=entry["key"],
                title=entry.get("key", "").rsplit("/", 1)[-1],
                mime=entry.get("content_type"),
                size=entry.get("size"),
                modified_at=modified_at,
                cursor_token=etag,
                raw=entry,
            )

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        data = await self._blob_store.get(sd.source_uri)
        return FetchedDoc(
            data=data,
            mime=sd.mime or "application/octet-stream",
            meta={"etag": sd.cursor_token},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet()

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(FileUploadConnector)
