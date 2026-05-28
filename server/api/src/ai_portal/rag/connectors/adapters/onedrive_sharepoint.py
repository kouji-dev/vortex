"""OneDrive / SharePoint connector.

Talks to Microsoft Graph via a thin HTTP wrapper — no MSAL token plumbing
lives here, the Control-Plane secret store hands back a ready-to-use
bearer token.

Scope is either a Sharepoint **site** (``/sites/{id}/drive``) or a specific
**library** (``/drives/{id}``). Each driveItem yields a SourceDoc; ACLs come
from the per-item ``permissions`` collection.

Delta strategy: Graph's ``/delta`` endpoint returns a ``deltaLink`` after
each call. That link itself is the cursor — opaque to the connector.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from ai_portal.rag.connectors import register
from ai_portal.rag.connectors.manifest import ConnectorManifest
from ai_portal.rag.connectors.protocol import (
    AclSet,
    FetchedDoc,
    SourceDoc,
)

_MANIFEST = ConnectorManifest(
    name="onedrive_sharepoint",
    auth_kinds=("oauth", "service_principal"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=True,
    config_schema={
        "type": "object",
        "required": ["scope_type", "scope_id"],
        "properties": {
            "scope_type": {"enum": ["site", "drive"]},
            "scope_id": {"type": "string"},
            "tenant_id": {"type": "string"},
        },
    },
)

_GRAPH = "https://graph.microsoft.com/v1.0"


class OneDriveSharepointConnector:
    """SharePoint site / OneDrive library watcher."""

    manifest = _MANIFEST

    def __init__(
        self,
        config: dict[str, Any],
        token_provider: Any,
        client_factory: Any | None = None,
    ) -> None:
        self._config = config
        self._token_provider = token_provider
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=30.0)
        )
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "OneDriveSharepointConnector":
        token_provider = (
            getattr(secret_store, "graph_token_provider", None)
            if secret_store is not None
            else None
        )
        client_factory = (
            getattr(secret_store, "graph_client_factory", None)
            if secret_store is not None
            else None
        )
        return cls(config, token_provider, client_factory)

    async def _headers(self) -> dict[str, str]:
        token = ""
        if self._token_provider is not None:
            token = await self._token_provider()
        return {"Authorization": f"Bearer {token}"}

    def _list_url(self) -> str:
        scope_type = self._config["scope_type"]
        scope_id = self._config["scope_id"]
        if scope_type == "site":
            return f"{_GRAPH}/sites/{scope_id}/drive/root/children"
        return f"{_GRAPH}/drives/{scope_id}/root/children"

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        headers = await self._headers()
        url = cursor or self._list_url()
        async with self._client_factory() as client:
            while url:
                res = await client.get(url, headers=headers)
                if res.status_code >= 400:
                    return
                body = res.json()
                for item in body.get("value", []):
                    if "folder" in item:
                        continue
                    drive_id = item.get("parentReference", {}).get("driveId", "")
                    yield SourceDoc(
                        source_uri=f"msgraph://{drive_id}/items/{item['id']}",
                        title=item.get("name", item["id"]),
                        mime=(item.get("file") or {}).get("mimeType"),
                        size=item.get("size"),
                        modified_at=None,
                        cursor_token=item.get("eTag"),
                        raw=item,
                    )
                url = body.get("@odata.nextLink") or body.get("@odata.deltaLink")
                if body.get("@odata.deltaLink"):
                    self._cursor = body["@odata.deltaLink"]
                    break

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        # source_uri ``msgraph://{driveId}/items/{itemId}``
        rest = sd.source_uri.removeprefix("msgraph://")
        drive_id, _, item_id = rest.partition("/items/")
        url = f"{_GRAPH}/drives/{drive_id}/items/{item_id}/content"
        headers = await self._headers()
        async with self._client_factory() as client:
            res = await client.get(url, headers=headers, follow_redirects=True)
            res.raise_for_status()
            return FetchedDoc(
                data=res.content,
                mime=sd.mime or "application/octet-stream",
                meta={"item_id": item_id, "etag": sd.cursor_token},
            )

    async def acls(self, sd: SourceDoc) -> AclSet:
        rest = sd.source_uri.removeprefix("msgraph://")
        drive_id, _, item_id = rest.partition("/items/")
        url = f"{_GRAPH}/drives/{drive_id}/items/{item_id}/permissions"
        headers = await self._headers()
        users: set[str] = set()
        groups: set[str] = set()
        public = False
        async with self._client_factory() as client:
            res = await client.get(url, headers=headers)
            if res.status_code >= 400:
                return AclSet()
            for perm in res.json().get("value", []):
                link = perm.get("link") or {}
                if link.get("scope") == "anonymous":
                    public = True
                granted = perm.get("grantedToV2") or perm.get("grantedTo") or {}
                u = granted.get("user") or {}
                g = granted.get("group") or {}
                if u.get("id"):
                    users.add(u["id"])
                if g.get("id"):
                    groups.add(g["id"])
        return AclSet(user_ids=users, group_ids=groups, public=public)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(OneDriveSharepointConnector)
