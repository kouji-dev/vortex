"""Jira connector.

Walks issues under a project scope. Each issue (body + rendered comments)
is one SourceDoc; attachments are emitted as child SourceDocs.

SDK (``atlassian-python-api``) is hidden behind ``_JiraClient`` so tests
inject a fake.

ACL: project users (account ids). Delta: highest ``updated`` timestamp.
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
    name="jira",
    auth_kinds=("token", "basic", "oauth"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=True,
    config_schema={
        "type": "object",
        "required": ["base_url", "project_key"],
        "properties": {
            "base_url": {"type": "string"},
            "project_key": {"type": "string"},
            "include_attachments": {"type": "boolean", "default": True},
        },
    },
)


class _JiraClient:
    """Lazy wrapper around ``atlassian.Jira``."""

    def __init__(self, base_url: str, auth: dict[str, Any] | None) -> None:
        self._base_url = base_url
        self._auth = auth or {}
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from atlassian import Jira  # type: ignore

            self._svc = Jira(url=self._base_url, **self._auth)
        return self._svc

    async def list_issues(self, project_key: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        res = svc.jql(f"project = {project_key}", limit=100)
        return list((res or {}).get("issues", []))

    async def get_attachment_bytes(self, attachment_id: str) -> bytes:
        svc = self._resolve()
        return svc.get_attachment_content(attachment_id)

    async def list_project_users(self, project_key: str) -> list[str]:
        svc = self._resolve()
        return [u["accountId"] for u in svc.get_all_project_users(project_key) or []]


class JiraConnector:
    """Jira project walker — issues + attachments + project users ACL."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "JiraConnector":
        client = (
            getattr(secret_store, "jira_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            auth = (
                getattr(secret_store, "jira_auth", lambda: {})()
                if secret_store is not None
                else {}
            )
            client = _JiraClient(config["base_url"], auth)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        project_key = self._config["project_key"]
        issues = await self._client.list_issues(project_key)
        max_ts = cursor
        include_atts = self._config.get("include_attachments", True)
        for issue in issues:
            key = issue.get("key", issue.get("id"))
            fields = issue.get("fields") or {}
            upd = fields.get("updated")
            if cursor and upd and upd <= cursor:
                continue
            if upd and (max_ts is None or upd > max_ts):
                max_ts = upd
            yield SourceDoc(
                source_uri=f"jira://{project_key}/{key}",
                title=fields.get("summary", key),
                mime="text/plain",
                size=len(fields.get("description") or "") or None,
                modified_at=None,
                cursor_token=upd,
                raw={
                    "project_key": project_key,
                    "key": key,
                    "fields": fields,
                    "kind": "issue",
                },
            )
            if include_atts:
                for att in fields.get("attachment") or []:
                    aid = att.get("id")
                    yield SourceDoc(
                        source_uri=f"jira://{project_key}/{key}/attachments/{aid}",
                        title=att.get("filename", str(aid)),
                        mime=att.get("mimeType"),
                        size=att.get("size"),
                        modified_at=None,
                        cursor_token=upd,
                        raw={
                            "project_key": project_key,
                            "key": key,
                            "attachment": att,
                            "kind": "attachment",
                        },
                    )
        if max_ts:
            self._cursor = max_ts

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        if sd.raw.get("kind") == "attachment":
            aid = sd.raw["attachment"]["id"]
            data = await self._client.get_attachment_bytes(aid)
            return FetchedDoc(
                data=data,
                mime=sd.mime or "application/octet-stream",
                meta={"filename": sd.raw["attachment"].get("filename")},
            )
        fields = sd.raw["fields"]
        body = fields.get("description") or ""
        for c in fields.get("comment", {}).get("comments") or []:
            body += "\n\n---\n" + (c.get("body") or "")
        return FetchedDoc(
            data=body.encode("utf-8"),
            mime="text/plain",
            meta={"issue_key": sd.raw["key"]},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        project_key = sd.raw.get("project_key")
        if not project_key:
            return AclSet()
        try:
            users = await self._client.list_project_users(project_key)
        except Exception:
            return AclSet()
        return AclSet(user_ids=set(users))

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(JiraConnector)
