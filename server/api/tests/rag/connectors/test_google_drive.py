"""google_drive connector — discover + acls with a fake Drive API."""

from __future__ import annotations

import pytest


class _FakeDriveClient:
    def __init__(self):
        self._files = [
            {
                "id": "f1",
                "name": "Plan.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-05-01T00:00:00Z",
                "size": "10",
                "version": "100",
            },
            {
                "id": "f2",
                "name": "Notes.txt",
                "mimeType": "text/plain",
                "modifiedTime": "2026-05-02T00:00:00Z",
                "size": "5",
                "version": "200",
            },
        ]
        self._perms = {
            "f1": [
                {"emailAddress": "alice@x.test", "type": "user", "id": "u1"},
                {"emailAddress": "team@x.test", "type": "group", "id": "g1"},
            ],
            "f2": [
                {"type": "anyone", "id": "anyone"},
            ],
        }

    async def list_files(self, scope_type, scope_id):
        return list(self._files)

    async def get_bytes(self, file_id):
        return f"gdrive:{file_id}".encode()

    async def list_permissions(self, file_id):
        return list(self._perms.get(file_id, []))


class _SecretStore:
    def __init__(self, client):
        self.google_drive_client = client

    def google_drive_credentials(self):
        return None


@pytest.mark.asyncio
async def test_drive_discover_and_acls():
    from ai_portal.rag.connectors.adapters.google_drive import GoogleDriveConnector

    client = _FakeDriveClient()
    conn = await GoogleDriveConnector.setup(
        config={"scope_type": "folder", "scope_id": "FOLDER123"},
        secret_store=_SecretStore(client),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert {d.source_uri for d in docs} == {
        "gdrive://f1",
        "gdrive://f2",
    }

    f1 = next(d for d in docs if d.source_uri == "gdrive://f1")
    f2 = next(d for d in docs if d.source_uri == "gdrive://f2")

    acl1 = await conn.acls(f1)
    assert acl1.user_ids == {"alice@x.test"}
    assert acl1.group_ids == {"team@x.test"}
    assert acl1.public is False

    acl2 = await conn.acls(f2)
    assert acl2.public is True

    fetched = await conn.fetch(f1)
    assert fetched.data == b"gdrive:f1"


@pytest.mark.asyncio
async def test_drive_delta_cursor_skips_older_versions():
    from ai_portal.rag.connectors.adapters.google_drive import GoogleDriveConnector

    conn = await GoogleDriveConnector.setup(
        config={"scope_type": "folder", "scope_id": "F"},
        secret_store=_SecretStore(_FakeDriveClient()),
    )
    docs = [sd async for sd in conn.discover(cursor="100")]
    assert [d.source_uri for d in docs] == ["gdrive://f2"]
