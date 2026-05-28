"""S3 bucket connector.

Uses the Control-Plane :class:`BlobStore` abstraction so the same code path
works for AWS S3, MinIO, and any other S3-compatible backend wired in.
The connector itself does NOT import boto3 — that lives in the BlobStore
provider.

Delta strategy: per-object ETag (S3 native). The orchestrator persists the
highest ``modified_at`` as the run-level cursor; per-object ETag is stored
on the document so an unchanged object is short-circuited.
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
    name="s3_bucket",
    auth_kinds=("token", "service_principal"),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["bucket", "prefix"],
        "properties": {
            "bucket": {"type": "string"},
            "prefix": {"type": "string"},
            "region": {"type": "string"},
            "endpoint_url": {"type": "string"},
        },
    },
)


class S3BucketConnector:
    """S3 (or S3-compatible) prefix watcher."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], blob_store: Any) -> None:
        self._config = config
        self._blob_store = blob_store
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "S3BucketConnector":
        # In production: secret_store hands back a per-bucket BlobStore.
        blob_store = (
            getattr(secret_store, "build_s3_store", lambda c: None)(config)
            if secret_store is not None
            else None
        )
        return cls(config, blob_store)

    def _qualified_key(self, key: str) -> str:
        return f"s3://{self._config['bucket']}/{key}"

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
        prefix = self._config["prefix"]
        for obj in await self._blob_store.list(prefix):
            mtime: datetime | None = obj.get("modified_at")
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
        # source_uri is ``s3://bucket/key`` — strip prefix back to key.
        key = sd.source_uri.split("/", 3)[-1]
        data = await self._blob_store.get(key)
        return FetchedDoc(
            data=data,
            mime=sd.mime or "application/octet-stream",
            meta={"etag": sd.cursor_token, "bucket": self._config["bucket"]},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet()

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(S3BucketConnector)
