"""Slack connector.

Walks an allow-listed set of channels via the Slack Web API. Each message
(root + thread reply) becomes a SourceDoc; file shares are emitted as
child SourceDocs of the message they appear in.

SDK is hidden behind ``_SlackClient`` — tests inject a fake.

ACL extraction: per-channel ``conversations.members`` list (the bot can
only see channels it's been added to). The user-id set becomes the ACL.

Delta strategy: messages have a Slack ``ts`` (Unix-epoch-with-decimals).
The cursor is the highest seen ``ts`` across all channels.
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
    name="slack",
    auth_kinds=("oauth", "token"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=True,
    config_schema={
        "type": "object",
        "required": ["channel_ids"],
        "properties": {
            "channel_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "include_threads": {"type": "boolean", "default": True},
            "include_files": {"type": "boolean", "default": True},
        },
    },
)


class _SlackClient:
    """Lazy wrapper around ``slack_sdk.web.async_client.AsyncWebClient``."""

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from slack_sdk.web.async_client import AsyncWebClient  # type: ignore

            self._svc = AsyncWebClient(token=self._token)
        return self._svc

    async def history(self, channel_id: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        res = await svc.conversations_history(channel=channel_id)
        return list(res.get("messages", []))

    async def replies(self, channel_id: str, ts: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        res = await svc.conversations_replies(channel=channel_id, ts=ts)
        # First message is the parent — skip.
        return list(res.get("messages", []))[1:]

    async def members(self, channel_id: str) -> list[str]:
        svc = self._resolve()
        res = await svc.conversations_members(channel=channel_id)
        return list(res.get("members", []))


class SlackConnector:
    """Slack channel walker — messages + threads + files."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "SlackConnector":
        client = (
            getattr(secret_store, "slack_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            token = (
                getattr(secret_store, "slack_token", lambda: None)()
                if secret_store is not None
                else None
            )
            client = _SlackClient(token)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        max_ts = cursor
        include_threads = self._config.get("include_threads", True)
        include_files = self._config.get("include_files", True)
        for channel_id in self._config["channel_ids"]:
            messages = await self._client.history(channel_id)
            for msg in messages:
                ts = msg.get("ts")
                if cursor and ts and ts <= cursor:
                    continue
                if ts and (max_ts is None or ts > max_ts):
                    max_ts = ts
                yield _msg_doc(channel_id, msg)
                if include_files:
                    for f in msg.get("files") or []:
                        yield _file_doc(channel_id, msg, f)
                if include_threads and msg.get("thread_ts") == ts and msg.get("reply_count", 0) > 0:
                    replies = await self._client.replies(channel_id, ts)
                    for r in replies:
                        rts = r.get("ts")
                        if cursor and rts and rts <= cursor:
                            continue
                        if rts and (max_ts is None or rts > max_ts):
                            max_ts = rts
                        yield _msg_doc(channel_id, r, parent_ts=ts)
        if max_ts:
            self._cursor = max_ts

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        text = sd.raw.get("text") or ""
        if sd.raw.get("kind") == "file":
            text = sd.raw.get("name") or ""
        return FetchedDoc(
            data=text.encode("utf-8"),
            mime="text/plain",
            meta={k: v for k, v in sd.raw.items() if k not in {"text"}},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        channel_id = sd.raw.get("channel_id", "")
        try:
            members = await self._client.members(channel_id)
        except Exception:
            return AclSet()
        return AclSet(user_ids=set(members))

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


def _msg_doc(channel_id: str, msg: dict, parent_ts: str | None = None) -> SourceDoc:
    ts = msg.get("ts", "")
    return SourceDoc(
        source_uri=f"slack://{channel_id}/messages/{ts}",
        title=(msg.get("text") or "")[:80] or ts,
        mime="text/plain",
        size=len(msg.get("text") or "") or None,
        modified_at=None,
        cursor_token=ts,
        raw={**msg, "channel_id": channel_id, "parent_ts": parent_ts, "kind": "message"},
    )


def _file_doc(channel_id: str, msg: dict, f: dict) -> SourceDoc:
    fid = f.get("id", "")
    return SourceDoc(
        source_uri=f"slack://{channel_id}/files/{fid}",
        title=f.get("name", fid),
        mime=f.get("mimetype"),
        size=f.get("size"),
        modified_at=None,
        cursor_token=msg.get("ts"),
        raw={**f, "channel_id": channel_id, "parent_ts": msg.get("ts"), "kind": "file"},
    )


register(SlackConnector)
