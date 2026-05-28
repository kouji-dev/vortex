"""confluence connector — discover + acls with a fake REST client."""

from __future__ import annotations

import pytest


class _FakeConfluenceClient:
    def __init__(self) -> None:
        self._pages = [
            {"id": "p1", "title": "Plan", "version": {"number": 3}},
            {"id": "p2", "title": "Notes", "version": {"number": 7}},
        ]
        self._bodies = {
            "p1": {
                "id": "p1",
                "body": {"storage": {"value": "<p>plan body</p>"}},
                "version": {"number": 3},
                "space": {"key": "ENG"},
            },
            "p2": {
                "id": "p2",
                "body": {"storage": {"value": "<p>notes body</p>"}},
                "version": {"number": 7},
                "space": {"key": "ENG"},
            },
        }

    async def list_pages(self, space_key):
        return list(self._pages)

    async def get_page(self, page_id):
        return self._bodies[page_id]

    async def space_restrictions(self, space_key):
        return {
            "users": [{"accountId": "u-alice"}],
            "groups": [{"name": "eng-team"}],
        }


class _SecretStore:
    def __init__(self, client):
        self.confluence_client = client


@pytest.mark.asyncio
async def test_confluence_discover_fetch_and_acls():
    from ai_portal.rag.connectors.adapters.confluence import ConfluenceConnector

    client = _FakeConfluenceClient()
    conn = await ConfluenceConnector.setup(
        config={"base_url": "https://x.atlassian.net/wiki", "space_key": "ENG"},
        secret_store=_SecretStore(client),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert {d.source_uri for d in docs} == {
        "confluence://ENG/p1",
        "confluence://ENG/p2",
    }
    fetched = await conn.fetch(docs[0])
    assert b"body" in fetched.data
    acl = await conn.acls(docs[0])
    assert acl.user_ids == {"u-alice"}
    assert acl.group_ids == {"eng-team"}
    assert acl.public is False


@pytest.mark.asyncio
async def test_confluence_delta_skips_old_versions():
    from ai_portal.rag.connectors.adapters.confluence import ConfluenceConnector

    conn = await ConfluenceConnector.setup(
        config={"base_url": "x", "space_key": "ENG"},
        secret_store=_SecretStore(_FakeConfluenceClient()),
    )
    docs = [sd async for sd in conn.discover(cursor="3")]
    assert [d.source_uri for d in docs] == ["confluence://ENG/p2"]
    assert await conn.delta_cursor() == "7"
