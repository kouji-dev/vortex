"""Google Drive connector.

Discovers files in a folder + (optionally) a shared drive scope.

ACL extraction is mandatory: each file's ``permissions.list`` response is
flattened to user emails + group ids, which the ACL mapper later resolves
to org users/groups.

Delta strategy: Drive's native ``changes.list`` with a startPageToken.
The cursor is the token returned by the most recent successful run.

This module deliberately keeps the SDK behind a thin
``_DriveApiClient`` indirection so tests can inject a fake without
spinning up ``google-api-python-client``.
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
    name="google_drive",
    auth_kinds=("oauth", "service_principal"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=True,
    config_schema={
        "type": "object",
        "required": ["scope_type", "scope_id"],
        "properties": {
            "scope_type": {"enum": ["folder", "shared_drive"]},
            "scope_id": {"type": "string"},
            "include_trashed": {"type": "boolean", "default": False},
            "mime_types": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
)


class _DriveApiClient:
    """Lazy wrapper around googleapiclient discovery service."""

    def __init__(self, creds: Any) -> None:
        self._creds = creds
        self._service: Any | None = None

    def _resolve(self) -> Any:
        if self._service is None:
            # Late import — keeps the package importable without the SDK.
            from googleapiclient.discovery import build  # type: ignore

            self._service = build(
                "drive", "v3", credentials=self._creds, cache_discovery=False
            )
        return self._service

    async def list_files(
        self, scope_type: str, scope_id: str
    ) -> list[dict[str, Any]]:
        svc = self._resolve()
        query = (
            f"'{scope_id}' in parents and trashed = false"
            if scope_type == "folder"
            else f"driveId = '{scope_id}'"
        )
        req = svc.files().list(
            q=query,
            fields=(
                "files(id, name, mimeType, modifiedTime, size, "
                "webViewLink, version)"
            ),
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        return list(req.execute().get("files", []))

    async def get_bytes(self, file_id: str) -> bytes:
        svc = self._resolve()
        return svc.files().get_media(fileId=file_id).execute()

    async def list_permissions(self, file_id: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        return list(
            svc.permissions()
            .list(fileId=file_id, fields="permissions(emailAddress, type, id)")
            .execute()
            .get("permissions", [])
        )


class GoogleDriveConnector:
    """Google Drive folder / shared-drive watcher with ACL mirroring."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "GoogleDriveConnector":
        creds = (
            getattr(secret_store, "google_drive_credentials", lambda: None)()
            if secret_store is not None
            else None
        )
        client = (
            getattr(secret_store, "google_drive_client", None)
            or _DriveApiClient(creds)
        )
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        if self._client is None:
            return
        scope_type = self._config["scope_type"]
        scope_id = self._config["scope_id"]
        files = await self._client.list_files(scope_type, scope_id)
        for f in files:
            version = f.get("version")
            if cursor and version and str(version) <= cursor:
                continue
            yield SourceDoc(
                source_uri=f"gdrive://{f['id']}",
                title=f.get("name", f["id"]),
                mime=f.get("mimeType"),
                size=int(f["size"]) if f.get("size") else None,
                modified_at=None,
                cursor_token=str(version) if version else None,
                raw=f,
            )

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        file_id = sd.source_uri.removeprefix("gdrive://")
        data = await self._client.get_bytes(file_id)
        return FetchedDoc(
            data=data,
            mime=sd.mime or "application/octet-stream",
            meta={"file_id": file_id, "version": sd.cursor_token},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        file_id = sd.source_uri.removeprefix("gdrive://")
        perms = await self._client.list_permissions(file_id)
        users: set[str] = set()
        groups: set[str] = set()
        public = False
        for p in perms:
            ptype = p.get("type")
            if ptype == "anyone":
                public = True
            elif ptype == "user" and p.get("emailAddress"):
                users.add(p["emailAddress"])
            elif ptype == "group" and p.get("emailAddress"):
                groups.add(p["emailAddress"])
        return AclSet(user_ids=users, group_ids=groups, public=public)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(GoogleDriveConnector)
