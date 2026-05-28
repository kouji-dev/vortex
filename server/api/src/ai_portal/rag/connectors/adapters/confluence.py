"""Confluence connector (Cloud + Server).

Talks to the Confluence REST API via a thin ``_ConfluenceClient`` indirection
so tests can inject a fake without importing ``atlassian-python-api``.

Scope is a single ``space_key``. Each page is one :class:`SourceDoc` whose
``cursor_token`` is the page version. Delta strategy: skip pages whose
version is <= the last applied cursor (string-compared, treating versions
as zero-padded numeric tokens).

ACL extraction is best-effort via the space-level read restrictions; if no
restriction is set the page is treated as readable by everyone with space
access (``public=True`` within the org).
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
    name="confluence",
    auth_kinds=("token", "basic", "oauth"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["base_url", "space_key"],
        "properties": {
            "base_url": {"type": "string"},
            "space_key": {"type": "string"},
            "mode": {"enum": ["cloud", "server"], "default": "cloud"},
        },
    },
)


class _ConfluenceClient:
    """Thin wrapper around atlassian.Confluence — lazy import."""

    def __init__(self, base_url: str, auth: Any) -> None:
        self._base_url = base_url
        self._auth = auth
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from atlassian import Confluence  # type: ignore

            self._svc = Confluence(url=self._base_url, **(self._auth or {}))
        return self._svc

    async def list_pages(self, space_key: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        return list(svc.get_all_pages_from_space(space=space_key, expand="version"))

    async def get_page(self, page_id: str) -> dict[str, Any]:
        svc = self._resolve()
        return svc.get_page_by_id(page_id, expand="body.storage,version,space")

    async def space_restrictions(self, space_key: str) -> dict[str, Any]:
        svc = self._resolve()
        return svc.get_space_permissions(space_key) or {}


class ConfluenceConnector:
    """Confluence space watcher with version-based delta and ACL mirroring."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "ConfluenceConnector":
        client = (
            getattr(secret_store, "confluence_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            auth = (
                getattr(secret_store, "confluence_auth", lambda: {})()
                if secret_store is not None
                else {}
            )
            client = _ConfluenceClient(config["base_url"], auth)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        space_key = self._config["space_key"]
        pages = await self._client.list_pages(space_key)
        max_version = cursor
        for p in pages:
            version = str((p.get("version") or {}).get("number", ""))
            if cursor and version and version <= cursor:
                continue
            if max_version is None or (version and version > max_version):
                max_version = version
            yield SourceDoc(
                source_uri=f"confluence://{space_key}/{p['id']}",
                title=p.get("title", p["id"]),
                mime="text/html",
                size=None,
                modified_at=None,
                cursor_token=version or None,
                raw=p,
            )
        if max_version:
            self._cursor = max_version

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        page_id = sd.source_uri.rsplit("/", 1)[-1]
        page = await self._client.get_page(page_id)
        body = ((page.get("body") or {}).get("storage") or {}).get("value", "")
        return FetchedDoc(
            data=body.encode("utf-8"),
            mime="text/html",
            meta={
                "page_id": page_id,
                "version": (page.get("version") or {}).get("number"),
                "space": (page.get("space") or {}).get("key"),
            },
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        space_key = self._config["space_key"]
        try:
            restrictions = await self._client.space_restrictions(space_key)
        except Exception:
            return AclSet(public=True)
        users: set[str] = set()
        groups: set[str] = set()
        for u in restrictions.get("users") or []:
            uid = u.get("accountId") or u.get("name") or u.get("username")
            if uid:
                users.add(uid)
        for g in restrictions.get("groups") or []:
            gid = g.get("name") or g.get("id")
            if gid:
                groups.add(gid)
        if not users and not groups:
            return AclSet(public=True)
        return AclSet(user_ids=users, group_ids=groups)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(ConfluenceConnector)
