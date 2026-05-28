"""IMAP shared-mailbox connector.

Pulls messages from a single IMAP folder/label. SDK (``imapclient``) is
hidden behind ``_ImapClient`` indirection so tests inject a fake without
opening a socket.

Each top-level message is one SourceDoc; attachments are emitted as child
SourceDocs (one per attachment, ``parent_uid`` set in raw).

ACL: a shared mailbox has flat read access — ``public=True`` within org.
Delta: highest seen UID per folder.
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
    name="imap_email",
    auth_kinds=("basic", "oauth"),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["host", "username", "folder"],
        "properties": {
            "host": {"type": "string"},
            "port": {"type": "integer", "default": 993},
            "username": {"type": "string"},
            "folder": {"type": "string", "default": "INBOX"},
            "label_filter": {"type": "string"},
            "include_attachments": {"type": "boolean", "default": True},
        },
    },
)


class _ImapClient:
    """Lazy wrapper around ``imapclient.IMAPClient``."""

    def __init__(self, host: str, port: int, username: str, password: str | None) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from imapclient import IMAPClient  # type: ignore

            self._svc = IMAPClient(self._host, port=self._port, ssl=True)
            self._svc.login(self._username, self._password or "")
        return self._svc

    async def search(self, folder: str, label: str | None) -> list[int]:
        svc = self._resolve()
        svc.select_folder(folder, readonly=True)
        if label:
            return list(svc.search(["X-GM-LABELS", label]))
        return list(svc.search(["ALL"]))

    async def fetch_message(self, uid: int) -> dict[str, Any]:
        svc = self._resolve()
        return svc.fetch([uid], ["BODY.PEEK[]", "FLAGS", "INTERNALDATE"])[uid]


class ImapEmailConnector:
    """IMAP shared-mailbox / label-filtered email walker."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "ImapEmailConnector":
        client = (
            getattr(secret_store, "imap_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            password = (
                getattr(secret_store, "imap_password", lambda: None)()
                if secret_store is not None
                else None
            )
            client = _ImapClient(
                config["host"],
                config.get("port", 993),
                config["username"],
                password,
            )
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        cursor_uid = int(cursor) if cursor else 0
        folder = self._config["folder"]
        label = self._config.get("label_filter")
        uids = await self._client.search(folder, label)
        max_uid = cursor_uid
        include_atts = self._config.get("include_attachments", True)
        for uid in uids:
            if uid <= cursor_uid:
                continue
            if uid > max_uid:
                max_uid = uid
            msg = await self._client.fetch_message(uid)
            subject = msg.get("subject") or f"uid={uid}"
            yield SourceDoc(
                source_uri=f"imap://{folder}/{uid}",
                title=subject,
                mime="message/rfc822",
                size=msg.get("size"),
                modified_at=None,
                cursor_token=str(uid),
                raw={"uid": uid, "folder": folder, "msg": msg, "kind": "message"},
            )
            if include_atts:
                for att in msg.get("attachments") or []:
                    aid = att.get("id") or att.get("filename", "att")
                    yield SourceDoc(
                        source_uri=f"imap://{folder}/{uid}/att/{aid}",
                        title=att.get("filename", aid),
                        mime=att.get("content_type"),
                        size=att.get("size"),
                        modified_at=None,
                        cursor_token=str(uid),
                        raw={
                            "parent_uid": uid,
                            "folder": folder,
                            "att": att,
                            "kind": "attachment",
                        },
                    )
        if max_uid > cursor_uid:
            self._cursor = str(max_uid)

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        if sd.raw.get("kind") == "attachment":
            att = sd.raw["att"]
            return FetchedDoc(
                data=att.get("data", b""),
                mime=att.get("content_type") or "application/octet-stream",
                meta={"filename": att.get("filename")},
            )
        msg = sd.raw["msg"]
        body = msg.get("body") or msg.get("text") or ""
        if isinstance(body, str):
            body = body.encode("utf-8")
        return FetchedDoc(
            data=body,
            mime="message/rfc822",
            meta={"subject": msg.get("subject"), "from": msg.get("from")},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet(public=True)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(ImapEmailConnector)
