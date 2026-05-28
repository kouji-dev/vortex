"""Generic HTTP API connector.

Configurable cursor-paginated fetcher with JSONPath-style extractors for
the four canonical fields ``source_uri``, ``title``, ``body``, and
``modified_at``.

JSONPath here is a small subset (``.`` separator + numeric indices) so we
don't take a hard dep on a JSONPath library; tests can rely on the same
syntax.

Auth modes: ``bearer`` (header), ``basic`` (b64), ``api_key`` (header
named by config).

ACL: returns ``public=True`` — generic API has no user identity surface.
Delta: configurable ``cursor_param`` query argument plus a
``next_cursor_path`` JSONPath pointing at the next-page cursor in the
response payload.
"""

from __future__ import annotations

import base64
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
    name="generic_http",
    auth_kinds=("none", "token", "basic"),
    schedulable=True,
    supports_delta=True,
    supports_acl=False,
    supports_webhook=False,
    config_schema={
        "type": "object",
        "required": ["url", "items_path"],
        "properties": {
            "url": {"type": "string"},
            "method": {"enum": ["GET", "POST"], "default": "GET"},
            "auth": {
                "type": "object",
                "properties": {
                    "kind": {"enum": ["none", "bearer", "basic", "api_key"]},
                    "header_name": {"type": "string", "default": "X-Api-Key"},
                },
            },
            "items_path": {"type": "string"},
            "source_uri_path": {"type": "string", "default": "id"},
            "title_path": {"type": "string", "default": "title"},
            "body_path": {"type": "string", "default": "body"},
            "modified_at_path": {"type": "string"},
            "cursor_param": {"type": "string"},
            "next_cursor_path": {"type": "string"},
            "max_pages": {"type": "integer", "default": 50},
        },
    },
)


def _jp(obj: Any, path: str) -> Any:
    """Tiny JSONPath: dotted keys + ``[i]`` numeric indices."""

    if not path:
        return obj
    cur = obj
    for raw in path.split("."):
        # support items[0] form
        keys = []
        token = raw
        while "[" in token and token.endswith("]"):
            idx_start = token.rindex("[")
            keys.append(int(token[idx_start + 1 : -1]))
            token = token[:idx_start]
        if token:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(token)
        for k in reversed(keys):
            if not isinstance(cur, list) or k >= len(cur):
                return None
            cur = cur[k]
    return cur


class HttpGenericConnector:
    """Cursor-paginated HTTP-API walker with JSONPath extractors."""

    manifest = _MANIFEST

    def __init__(
        self,
        config: dict[str, Any],
        secret_value: str | None,
        client_factory: Any | None = None,
    ) -> None:
        self._config = config
        self._secret = secret_value
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=30.0)
        )
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "HttpGenericConnector":
        secret = (
            getattr(secret_store, "http_generic_secret", lambda: None)()
            if secret_store is not None
            else None
        )
        client_factory = (
            getattr(secret_store, "http_client_factory", None)
            if secret_store is not None
            else None
        )
        return cls(config, secret, client_factory)

    def _auth_headers(self) -> dict[str, str]:
        auth = self._config.get("auth") or {}
        kind = auth.get("kind", "none")
        if kind == "bearer" and self._secret:
            return {"Authorization": f"Bearer {self._secret}"}
        if kind == "basic" and self._secret:
            return {
                "Authorization": "Basic "
                + base64.b64encode(self._secret.encode()).decode()
            }
        if kind == "api_key" and self._secret:
            return {auth.get("header_name", "X-Api-Key"): self._secret}
        return {}

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        url = self._config["url"]
        method = self._config.get("method", "GET")
        cursor_param = self._config.get("cursor_param")
        max_pages = self._config.get("max_pages", 50)
        current_cursor = cursor
        new_cursor: str | None = current_cursor

        headers = self._auth_headers()
        async with self._client_factory() as client:
            for _ in range(max_pages):
                params: dict[str, str] = {}
                if cursor_param and current_cursor:
                    params[cursor_param] = current_cursor
                req = client.build_request(
                    method, url, params=params, headers=headers
                )
                res = await client.send(req)
                if res.status_code >= 400:
                    return
                body = res.json()
                items = _jp(body, self._config["items_path"]) or []
                for it in items:
                    suri_raw = _jp(it, self._config.get("source_uri_path", "id"))
                    if suri_raw is None:
                        continue
                    title = _jp(it, self._config.get("title_path", "title"))
                    modified = (
                        _jp(it, self._config["modified_at_path"])
                        if self._config.get("modified_at_path")
                        else None
                    )
                    yield SourceDoc(
                        source_uri=str(suri_raw),
                        title=str(title) if title else str(suri_raw),
                        mime="application/json",
                        size=None,
                        modified_at=None,
                        cursor_token=str(modified) if modified else None,
                        raw=it,
                    )
                next_cursor_path = self._config.get("next_cursor_path")
                if not next_cursor_path:
                    break
                next_cursor = _jp(body, next_cursor_path)
                if not next_cursor:
                    break
                current_cursor = str(next_cursor)
                new_cursor = current_cursor
        if new_cursor:
            self._cursor = new_cursor

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        body = _jp(sd.raw, self._config.get("body_path", "body")) or ""
        if not isinstance(body, (str, bytes)):
            import json

            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        return FetchedDoc(data=body, mime="text/plain", meta={"source_uri": sd.source_uri})

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet(public=True)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(HttpGenericConnector)
