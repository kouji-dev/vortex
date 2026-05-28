"""Google Cloud Storage connector.

Delta strategy uses GCS object ``generation`` (monotonically increasing per
object). The cursor is the maximum generation seen — both globally on the
run and per-object on the document.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ai_portal.rag.connectors import register
from ai_portal.rag.connectors.manifest import ConnectorManifest
from ai_portal.rag.connectors.protocol import (
    AclSet,
    FetchedDoc,
    SourceDoc,
)

_MANIFEST = ConnectorManifest(
    name="gcs_bucket",
    auth_kinds=("service_principal",),
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
        },
    },
)


class GcsBucketConnector:
    """GCS prefix watcher (generation-cursored)."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], blob_store: Any) -> None:
        self._config = config
        self._blob_store = blob_store
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "GcsBucketConnector":
        blob_store = (
            getattr(secret_store, "build_gcs_store", lambda c: None)(config)
            if secret_store is not None
            else None
        )
        return cls(config, blob_store)

    def _qualified_key(self, key: str) -> str:
        return f"gs://{self._config['bucket']}/{key}"

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        if self._blob_store is None:
            return
        cursor_gen = int(cursor) if cursor and cursor.isdigit() else None
        for obj in await self._blob_store.list(self._config["prefix"]):
            gen = obj.get("generation")
            if cursor_gen is not None and gen is not None and gen <= cursor_gen:
                continue
            yield SourceDoc(
                source_uri=self._qualified_key(obj["key"]),
                title=obj.get("key", "").rsplit("/", 1)[-1],
                mime=obj.get("content_type"),
                size=obj.get("size"),
                modified_at=obj.get("modified_at"),
                cursor_token=str(gen) if gen is not None else None,
                raw=obj,
            )

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        # source_uri ``gs://bucket/key`` → key after 3rd slash.
        key = sd.source_uri.split("/", 3)[-1]
        data = await self._blob_store.get(key)
        return FetchedDoc(
            data=data,
            mime=sd.mime or "application/octet-stream",
            meta={"generation": sd.cursor_token, "bucket": self._config["bucket"]},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet()

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(GcsBucketConnector)
