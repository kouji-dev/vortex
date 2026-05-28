"""Azure Blob Storage connector.

Mirrors the S3 connector shape — same BlobStore abstraction, just bound to
Azure credentials (service principal). Delta via per-blob ETag.
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
    name="azure_blob",
    auth_kinds=("service_principal", "token"),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["account", "container", "prefix"],
        "properties": {
            "account": {"type": "string"},
            "container": {"type": "string"},
            "prefix": {"type": "string"},
        },
    },
)


class AzureBlobConnector:
    """Azure Blob container/prefix watcher."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], blob_store: Any) -> None:
        self._config = config
        self._blob_store = blob_store
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "AzureBlobConnector":
        blob_store = (
            getattr(secret_store, "build_azure_store", lambda c: None)(config)
            if secret_store is not None
            else None
        )
        return cls(config, blob_store)

    def _qualified_key(self, key: str) -> str:
        return (
            f"azure://{self._config['account']}/"
            f"{self._config['container']}/{key}"
        )

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        if self._blob_store is None:
            return
        cursor_dt: datetime | None = None
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            except ValueError:
                cursor_dt = None
        for obj in await self._blob_store.list(self._config["prefix"]):
            mtime = obj.get("modified_at")
            if cursor_dt and mtime and mtime <= cursor_dt:
                continue
            yield SourceDoc(
                source_uri=self._qualified_key(obj["key"]),
                title=obj.get("key", "").rsplit("/", 1)[-1],
                mime=obj.get("content_type"),
                size=obj.get("size"),
                modified_at=mtime,
                cursor_token=obj.get("etag"),
                raw=obj,
            )

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        # source_uri ``azure://account/container/key`` → key after 4th slash.
        key = sd.source_uri.split("/", 4)[-1]
        data = await self._blob_store.get(key)
        return FetchedDoc(
            data=data,
            mime=sd.mime or "application/octet-stream",
            meta={"etag": sd.cursor_token, "container": self._config["container"]},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet()

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(AzureBlobConnector)
