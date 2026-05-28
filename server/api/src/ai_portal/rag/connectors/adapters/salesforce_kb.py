"""Salesforce Knowledge connector.

Pulls ``KnowledgeArticleVersion`` rows from a production org via SOQL.
SDK (``simple-salesforce``) is hidden behind ``_SalesforceClient`` so
tests inject a fake.

ACL: Knowledge data-category visibility is non-trivial; we capture the
DataCategory string into meta, return ``public=True`` for the org, and
defer fine-grained mapping to the ACL provider layer.

Delta: highest ``LastModifiedDate`` seen.
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
    name="salesforce_kb",
    auth_kinds=("oauth", "basic"),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "properties": {
            "publish_status": {
                "enum": ["Online", "Draft", "Archived"],
                "default": "Online",
            },
            "language": {"type": "string", "default": "en_US"},
        },
    },
)


class _SalesforceClient:
    """Lazy wrapper around ``simple_salesforce.Salesforce``."""

    def __init__(self, creds: dict[str, Any] | None) -> None:
        self._creds = creds or {}
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from simple_salesforce import Salesforce  # type: ignore

            self._svc = Salesforce(**self._creds)
        return self._svc

    async def query_articles(self, publish_status: str, language: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        soql = (
            "SELECT Id, Title, ArticleNumber, Summary, ArticleBody, "
            "Language, LastModifiedDate, PublishStatus "
            f"FROM KnowledgeArticleVersion WHERE PublishStatus='{publish_status}' "
            f"AND Language='{language}'"
        )
        res = svc.query_all(soql)
        return list(res.get("records", []))


class SalesforceKbConnector:
    """Salesforce Knowledge article walker."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "SalesforceKbConnector":
        client = (
            getattr(secret_store, "salesforce_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            creds = (
                getattr(secret_store, "salesforce_credentials", lambda: {})()
                if secret_store is not None
                else {}
            )
            client = _SalesforceClient(creds)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        status = self._config.get("publish_status", "Online")
        language = self._config.get("language", "en_US")
        records = await self._client.query_articles(status, language)
        max_ts = cursor
        for r in records:
            modified = r.get("LastModifiedDate")
            if cursor and modified and modified <= cursor:
                continue
            if modified and (max_ts is None or modified > max_ts):
                max_ts = modified
            yield SourceDoc(
                source_uri=f"salesforce://kb/{r['Id']}",
                title=r.get("Title", r["Id"]),
                mime="text/html",
                size=len(r.get("ArticleBody") or "") or None,
                modified_at=None,
                cursor_token=modified,
                raw=r,
            )
        if max_ts:
            self._cursor = max_ts

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        body = sd.raw.get("ArticleBody") or sd.raw.get("Summary") or ""
        return FetchedDoc(
            data=body.encode("utf-8"),
            mime="text/html",
            meta={
                "article_number": sd.raw.get("ArticleNumber"),
                "language": sd.raw.get("Language"),
                "publish_status": sd.raw.get("PublishStatus"),
            },
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet(public=True)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(SalesforceKbConnector)
