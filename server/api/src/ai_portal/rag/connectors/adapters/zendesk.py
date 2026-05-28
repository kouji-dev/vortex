"""Zendesk connector — Help-Center articles + (opt-in) tickets.

SDK (``zenpy``) hidden behind ``_ZendeskClient`` so tests inject a fake.

Tickets are opt-in via ``config.tickets_opt_in`` — when off, only articles
are emitted.

ACL: articles in a published section are public within the org; tickets
inherit submitter + assignee visibility. We capture both into raw for the
ACL provider, but return ``public=True`` for articles and
``user_ids={submitter, assignee}`` for tickets.

Delta: highest ``updated_at`` seen.
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
    name="zendesk",
    auth_kinds=("token", "oauth"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["subdomain"],
        "properties": {
            "subdomain": {"type": "string"},
            "tickets_opt_in": {"type": "boolean", "default": False},
        },
    },
)


class _ZendeskClient:
    """Lazy wrapper around ``zenpy.Zenpy``."""

    def __init__(self, creds: dict[str, Any] | None) -> None:
        self._creds = creds or {}
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from zenpy import Zenpy  # type: ignore

            self._svc = Zenpy(**self._creds)
        return self._svc

    async def list_articles(self) -> list[dict[str, Any]]:
        svc = self._resolve()
        return [
            {
                "id": a.id,
                "title": a.title,
                "body": a.body or "",
                "updated_at": a.updated_at,
                "section_id": a.section_id,
            }
            for a in svc.help_center.articles()
        ]

    async def list_tickets(self) -> list[dict[str, Any]]:
        svc = self._resolve()
        return [
            {
                "id": t.id,
                "subject": t.subject,
                "description": t.description or "",
                "updated_at": t.updated_at,
                "submitter_id": t.submitter_id,
                "assignee_id": t.assignee_id,
            }
            for t in svc.tickets()
        ]


class ZendeskConnector:
    """Zendesk articles + opt-in tickets walker."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "ZendeskConnector":
        client = (
            getattr(secret_store, "zendesk_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            creds = (
                getattr(secret_store, "zendesk_credentials", lambda: {})()
                if secret_store is not None
                else {}
            )
            client = _ZendeskClient(creds)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        max_ts = cursor
        for a in await self._client.list_articles():
            upd = a.get("updated_at")
            if cursor and upd and upd <= cursor:
                continue
            if upd and (max_ts is None or upd > max_ts):
                max_ts = upd
            yield SourceDoc(
                source_uri=f"zendesk://articles/{a['id']}",
                title=a.get("title", str(a["id"])),
                mime="text/html",
                size=len(a.get("body") or "") or None,
                modified_at=None,
                cursor_token=upd,
                raw={**a, "kind": "article"},
            )
        if self._config.get("tickets_opt_in", False):
            for t in await self._client.list_tickets():
                upd = t.get("updated_at")
                if cursor and upd and upd <= cursor:
                    continue
                if upd and (max_ts is None or upd > max_ts):
                    max_ts = upd
                yield SourceDoc(
                    source_uri=f"zendesk://tickets/{t['id']}",
                    title=t.get("subject", str(t["id"])),
                    mime="text/plain",
                    size=len(t.get("description") or "") or None,
                    modified_at=None,
                    cursor_token=upd,
                    raw={**t, "kind": "ticket"},
                )
        if max_ts:
            self._cursor = max_ts

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        if sd.raw.get("kind") == "ticket":
            return FetchedDoc(
                data=(sd.raw.get("description") or "").encode("utf-8"),
                mime="text/plain",
                meta={"ticket_id": sd.raw.get("id")},
            )
        return FetchedDoc(
            data=(sd.raw.get("body") or "").encode("utf-8"),
            mime="text/html",
            meta={"article_id": sd.raw.get("id"), "section_id": sd.raw.get("section_id")},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        if sd.raw.get("kind") == "article":
            return AclSet(public=True)
        users: set[str] = set()
        for k in ("submitter_id", "assignee_id"):
            v = sd.raw.get(k)
            if v is not None:
                users.add(str(v))
        return AclSet(user_ids=users)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(ZendeskConnector)
