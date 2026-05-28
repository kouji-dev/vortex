"""Notion connector.

Walks a workspace via a workspace-token. Discovers both databases (each row
becomes a SourceDoc) and pages. The SDK is hidden behind a thin
``_NotionClient`` indirection so tests inject a fake.

Delta strategy: Notion exposes ``last_edited_time`` per page. The cursor is
an ISO timestamp; pages older than the cursor are skipped.

ACL extraction: workspace-token bots have flat workspace-wide access. We
return ``public=True`` within the org and rely on KB-level visibility for
enforcement.
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
    name="notion",
    auth_kinds=("token",),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "properties": {
            "page_size": {"type": "integer", "default": 50},
        },
    },
)


class _NotionClient:
    """Lazy wrapper around ``notion_client.AsyncClient``."""

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from notion_client import Client  # type: ignore

            self._svc = Client(auth=self._token)
        return self._svc

    async def search(self, page_size: int) -> list[dict[str, Any]]:
        svc = self._resolve()
        return list(svc.search(page_size=page_size).get("results", []))

    async def get_page(self, page_id: str) -> dict[str, Any]:
        svc = self._resolve()
        return svc.pages.retrieve(page_id=page_id)

    async def get_blocks(self, page_id: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        return list(svc.blocks.children.list(block_id=page_id).get("results", []))


class NotionConnector:
    """Notion workspace walker with last-edited-time delta."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "NotionConnector":
        client = (
            getattr(secret_store, "notion_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            token = (
                getattr(secret_store, "notion_token", lambda: None)()
                if secret_store is not None
                else None
            )
            client = _NotionClient(token)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        page_size = self._config.get("page_size", 50)
        results = await self._client.search(page_size)
        max_edited = cursor
        for r in results:
            obj_id = r.get("id")
            edited = r.get("last_edited_time")
            if cursor and edited and edited <= cursor:
                continue
            if edited and (max_edited is None or edited > max_edited):
                max_edited = edited
            obj_type = r.get("object", "page")
            title = _extract_title(r) or obj_id
            yield SourceDoc(
                source_uri=f"notion://{obj_type}/{obj_id}",
                title=title,
                mime="text/plain",
                size=None,
                modified_at=None,
                cursor_token=edited,
                raw=r,
            )
        if max_edited:
            self._cursor = max_edited

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        page_id = sd.source_uri.rsplit("/", 1)[-1]
        blocks = await self._client.get_blocks(page_id)
        text = "\n".join(_block_to_text(b) for b in blocks)
        return FetchedDoc(
            data=text.encode("utf-8"),
            mime="text/plain",
            meta={"page_id": page_id, "block_count": len(blocks)},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet(public=True)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


def _extract_title(obj: dict[str, Any]) -> str | None:
    props = obj.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title") or []
            return "".join(p.get("plain_text", "") for p in parts) or None
    # Database object has a top-level title array.
    if isinstance(obj.get("title"), list):
        return "".join(p.get("plain_text", "") for p in obj["title"]) or None
    return None


def _block_to_text(block: dict[str, Any]) -> str:
    btype = block.get("type")
    if not btype:
        return ""
    inner = block.get(btype) or {}
    rt = inner.get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in rt)


register(NotionConnector)
