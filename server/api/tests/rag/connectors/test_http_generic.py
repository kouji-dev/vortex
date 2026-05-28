"""generic_http connector — cursor-paginated discovery with respx."""

from __future__ import annotations

import httpx
import pytest
import respx


def _client_factory():
    return httpx.AsyncClient(timeout=5.0)


class _SecretStore:
    http_client_factory = staticmethod(_client_factory)

    def http_generic_secret(self):
        return "k-secret"


@pytest.mark.asyncio
async def test_http_generic_paginates_and_extracts_fields():
    from ai_portal.rag.connectors.adapters.http_generic import (
        HttpGenericConnector,
    )

    page1 = {
        "items": [
            {"id": "a", "title": "A", "body": "body-a", "updated": "2026-05-01"},
            {"id": "b", "title": "B", "body": "body-b", "updated": "2026-05-02"},
        ],
        "next": "page2",
    }
    page2 = {
        "items": [
            {"id": "c", "title": "C", "body": "body-c", "updated": "2026-05-03"},
        ],
        "next": None,
    }

    with respx.mock(assert_all_called=False) as m:
        route2 = m.get("https://api.test/items", params={"cursor": "page2"}).mock(
            return_value=httpx.Response(200, json=page2)
        )
        route1 = m.get("https://api.test/items").mock(
            return_value=httpx.Response(200, json=page1)
        )
        conn = await HttpGenericConnector.setup(
            config={
                "url": "https://api.test/items",
                "items_path": "items",
                "source_uri_path": "id",
                "title_path": "title",
                "body_path": "body",
                "modified_at_path": "updated",
                "cursor_param": "cursor",
                "next_cursor_path": "next",
                "auth": {"kind": "bearer"},
                "max_pages": 5,
            },
            secret_store=_SecretStore(),
        )
        docs = [sd async for sd in conn.discover(cursor=None)]

    assert {d.source_uri for d in docs} == {"a", "b", "c"}
    a = next(d for d in docs if d.source_uri == "a")
    fetched = await conn.fetch(a)
    assert fetched.data == b"body-a"
    # Bearer header carried into request:
    assert route1.calls[0].request.headers["authorization"] == "Bearer k-secret"
    assert route2.called
