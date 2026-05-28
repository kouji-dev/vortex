"""onedrive_sharepoint connector — discover + acls with respx-mocked Graph."""

from __future__ import annotations

import httpx
import pytest
import respx


def _client_factory():
    return httpx.AsyncClient(timeout=5.0)


class _SecretStore:
    graph_client_factory = staticmethod(_client_factory)

    async def graph_token_provider(self):  # noqa: D401
        return "fake-token"


@pytest.mark.asyncio
async def test_sharepoint_discover_yields_msgraph_uris():
    from ai_portal.rag.connectors.adapters.onedrive_sharepoint import (
        OneDriveSharepointConnector,
    )

    list_url = (
        "https://graph.microsoft.com/v1.0/sites/SITE123/drive/root/children"
    )

    with respx.mock(assert_all_called=False) as m:
        m.get(list_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "i1",
                            "name": "doc.docx",
                            "size": 11,
                            "eTag": "etag-1",
                            "file": {"mimeType": "application/vnd.docx"},
                            "parentReference": {"driveId": "D1"},
                        },
                        {
                            "id": "subfolder",
                            "name": "sub",
                            "folder": {"childCount": 2},
                            "parentReference": {"driveId": "D1"},
                        },
                    ]
                },
            )
        )
        conn = await OneDriveSharepointConnector.setup(
            config={"scope_type": "site", "scope_id": "SITE123"},
            secret_store=_SecretStore(),
        )
        docs = [sd async for sd in conn.discover(cursor=None)]
    assert [d.source_uri for d in docs] == ["msgraph://D1/items/i1"]
    assert docs[0].cursor_token == "etag-1"


@pytest.mark.asyncio
async def test_sharepoint_acls_extracts_users_groups_public():
    from ai_portal.rag.connectors.adapters.onedrive_sharepoint import (
        OneDriveSharepointConnector,
    )
    from ai_portal.rag.connectors import SourceDoc

    perms_url = (
        "https://graph.microsoft.com/v1.0/drives/D1/items/i1/permissions"
    )
    with respx.mock(assert_all_called=False) as m:
        m.get(perms_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "grantedToV2": {"user": {"id": "U1"}},
                        },
                        {
                            "grantedToV2": {"group": {"id": "G1"}},
                        },
                        {
                            "link": {"scope": "anonymous"},
                        },
                    ]
                },
            )
        )
        conn = await OneDriveSharepointConnector.setup(
            config={"scope_type": "site", "scope_id": "SITE123"},
            secret_store=_SecretStore(),
        )
        sd = SourceDoc(
            source_uri="msgraph://D1/items/i1",
            title="x",
            mime=None,
            size=None,
            modified_at=None,
        )
        acl = await conn.acls(sd)
    assert acl.user_ids == {"U1"}
    assert acl.group_ids == {"G1"}
    assert acl.public is True
