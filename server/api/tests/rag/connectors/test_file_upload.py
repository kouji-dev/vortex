"""file_upload connector — discovery from a fake BlobStore."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


class _FakeBlobStore:
    def __init__(self, entries: list[dict]):
        self._entries = entries

    async def list(self, prefix: str):
        return [e for e in self._entries if e["key"].startswith(prefix)]

    async def get(self, key: str) -> bytes:
        return f"bytes-of-{key}".encode()


class _SecretStore:
    def __init__(self, blob_store):
        self.blob_store = blob_store


@pytest.mark.asyncio
async def test_file_upload_lists_prefix_with_etag_cursor():
    from ai_portal.rag.connectors.adapters.file_upload import FileUploadConnector

    bs = _FakeBlobStore(
        [
            {
                "key": "kb/1/uploads/a.pdf",
                "size": 10,
                "modified_at": datetime(2026, 5, 1, tzinfo=UTC),
                "etag": "etag-a",
                "content_type": "application/pdf",
            },
            {
                "key": "kb/1/uploads/b.txt",
                "size": 5,
                "modified_at": datetime(2026, 5, 2, tzinfo=UTC),
                "etag": "etag-b",
                "content_type": "text/plain",
            },
            {
                "key": "kb/2/other.pdf",  # different prefix
                "size": 1,
                "modified_at": datetime(2026, 5, 3, tzinfo=UTC),
                "etag": "etag-c",
            },
        ]
    )
    conn = await FileUploadConnector.setup(
        config={"prefix": "kb/1/uploads/"},
        secret_store=_SecretStore(bs),
    )
    docs = [sd async for sd in conn.discover(cursor=None)]
    assert {d.source_uri for d in docs} == {
        "kb/1/uploads/a.pdf",
        "kb/1/uploads/b.txt",
    }
    fetched = await conn.fetch(docs[0])
    assert fetched.data.startswith(b"bytes-of-")


@pytest.mark.asyncio
async def test_file_upload_delta_skips_older_entries():
    from ai_portal.rag.connectors.adapters.file_upload import FileUploadConnector

    bs = _FakeBlobStore(
        [
            {
                "key": "p/a",
                "modified_at": datetime(2026, 1, 1, tzinfo=UTC),
                "etag": "1",
            },
            {
                "key": "p/b",
                "modified_at": datetime(2026, 6, 1, tzinfo=UTC),
                "etag": "2",
            },
        ]
    )
    conn = await FileUploadConnector.setup(
        config={"prefix": "p/"}, secret_store=_SecretStore(bs)
    )
    docs = [sd async for sd in conn.discover(cursor="2026-03-01T00:00:00+00:00")]
    assert [d.source_uri for d in docs] == ["p/b"]
