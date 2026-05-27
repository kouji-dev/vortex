"""Tests for :class:`GcsBlobStore`.

Patches the GCS ``Client``/``Bucket``/``Blob`` chain with a tiny in-memory
fake so we exercise the provider without touching Google Cloud or
launching a fake server.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.api_core.exceptions import NotFound

from ai_portal.storage.protocol import BlobNotFound
from ai_portal.storage.providers.gcs import GcsBlobStore

BUCKET = "gcs-test-bucket"


class _FakeBlob:
    def __init__(
        self, store: dict[str, tuple[bytes, str]], name: str
    ) -> None:
        self._store = store
        self.name = name

    def upload_from_string(self, data: bytes, *, content_type: str) -> None:
        self._store[self.name] = (data, content_type)

    def download_as_bytes(self) -> bytes:
        if self.name not in self._store:
            raise NotFound(f"missing: {self.name}")
        return self._store[self.name][0]

    def delete(self) -> None:
        if self.name not in self._store:
            raise NotFound(f"missing: {self.name}")
        del self._store[self.name]

    def generate_signed_url(
        self,
        *,
        version: str,
        expiration: Any,
        method: str,
        content_type: str | None = None,
    ) -> str:
        seconds = (
            int(expiration.total_seconds())
            if hasattr(expiration, "total_seconds")
            else int(expiration)
        )
        ct = f"&ct={content_type}" if content_type else ""
        return (
            f"https://storage.googleapis.com/{BUCKET}/{self.name}"
            f"?ver={version}&method={method}&exp={seconds}{ct}"
        )


class _FakeBucket:
    def __init__(
        self, name: str, store: dict[str, tuple[bytes, str]]
    ) -> None:
        self.name = name
        self._store = store

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(self._store, key)


class _FakeClient:
    def __init__(self, store: dict[str, tuple[bytes, str]]) -> None:
        self._store = store

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(name, self._store)


@pytest.fixture
def gcs_backend() -> dict[str, tuple[bytes, str]]:
    return {}


@pytest.fixture
def gcs_store(gcs_backend: dict[str, tuple[bytes, str]]) -> GcsBlobStore:
    return GcsBlobStore(BUCKET, client=_FakeClient(gcs_backend))


@pytest.mark.asyncio
async def test_put_returns_gs_uri(gcs_store: GcsBlobStore) -> None:
    url = await gcs_store.put("a/b.txt", b"data", "text/plain")
    assert url == f"gs://{BUCKET}/a/b.txt"


@pytest.mark.asyncio
async def test_put_persists_content_type(
    gcs_store: GcsBlobStore,
    gcs_backend: dict[str, tuple[bytes, str]],
) -> None:
    await gcs_store.put("a.json", b"{}", "application/json")
    assert gcs_backend["a.json"] == (b"{}", "application/json")


@pytest.mark.asyncio
async def test_put_get_roundtrip(gcs_store: GcsBlobStore) -> None:
    await gcs_store.put("k", b"\xff\xfeABC", "application/octet-stream")
    assert await gcs_store.get("k") == b"\xff\xfeABC"


@pytest.mark.asyncio
async def test_get_missing_raises(gcs_store: GcsBlobStore) -> None:
    with pytest.raises(BlobNotFound):
        await gcs_store.get("nope")


@pytest.mark.asyncio
async def test_delete_idempotent(gcs_store: GcsBlobStore) -> None:
    await gcs_store.delete("missing")
    await gcs_store.put("k", b"v", "text/plain")
    await gcs_store.delete("k")
    await gcs_store.delete("k")  # second delete no-op
    with pytest.raises(BlobNotFound):
        await gcs_store.get("k")


@pytest.mark.asyncio
async def test_presign_get_uses_v4_signing(gcs_store: GcsBlobStore) -> None:
    await gcs_store.put("k", b"v", "text/plain")
    url = await gcs_store.presign_get("k", 600)
    assert "ver=v4" in url
    assert "method=GET" in url
    assert "exp=600" in url


@pytest.mark.asyncio
async def test_presign_put_includes_content_type(
    gcs_store: GcsBlobStore,
) -> None:
    url = await gcs_store.presign_put("k", "image/png", 900)
    assert "method=PUT" in url
    assert "ct=image/png" in url


def test_client_override_path() -> None:
    """Explicit ``client=`` short-circuits the default constructor path."""
    fake = _FakeClient({})
    store = GcsBlobStore(BUCKET, client=fake)
    assert store._get_client() is fake
