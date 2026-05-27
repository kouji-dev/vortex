"""Protocol-level contract tests for BlobStore.

Every provider must satisfy these. Per-provider files instantiate the
fixture; this file owns the behavioural contract.
"""

from __future__ import annotations

import pytest

from ai_portal.storage.protocol import BlobNotFound, BlobStore


def test_protocol_exports() -> None:
    """``BlobStore`` is importable as a Protocol with the agreed methods."""
    expected = {"put", "get", "delete", "presign_get", "presign_put"}
    actual = {m for m in dir(BlobStore) if not m.startswith("_")}
    missing = expected - actual
    assert not missing, f"BlobStore missing methods: {missing}"


def test_blob_not_found_is_key_error() -> None:
    """``BlobNotFound`` is a ``KeyError`` so callers can catch broadly."""
    assert issubclass(BlobNotFound, KeyError)


@pytest.mark.asyncio
async def test_put_get_roundtrip_contract() -> None:
    """Sanity: the in-memory fake satisfies the protocol."""
    store = _FakeStore()
    url = await store.put("a/b.txt", b"hello", "text/plain")
    assert url
    assert await store.get("a/b.txt") == b"hello"


@pytest.mark.asyncio
async def test_get_missing_raises_blob_not_found() -> None:
    store = _FakeStore()
    with pytest.raises(BlobNotFound):
        await store.get("nope")


@pytest.mark.asyncio
async def test_delete_is_idempotent() -> None:
    store = _FakeStore()
    await store.delete("never-existed")
    await store.put("x", b"y", "text/plain")
    await store.delete("x")
    await store.delete("x")  # second delete must not raise
    with pytest.raises(BlobNotFound):
        await store.get("x")


@pytest.mark.asyncio
async def test_presign_get_returns_url_string() -> None:
    store = _FakeStore()
    await store.put("k", b"v", "text/plain")
    url = await store.presign_get("k", 60)
    assert isinstance(url, str) and url


@pytest.mark.asyncio
async def test_presign_put_returns_url_string() -> None:
    store = _FakeStore()
    url = await store.presign_put("k", "application/json", 60)
    assert isinstance(url, str) and url


class _FakeStore:
    """In-memory BlobStore used to lock in the protocol semantics."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        del content_type
        self._data[key] = data
        return f"mem://{key}"

    async def get(self, key: str) -> bytes:
        if key not in self._data:
            raise BlobNotFound(key)
        return self._data[key]

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def presign_get(self, key: str, expires_in: int) -> str:
        return f"mem://{key}?op=get&exp={expires_in}"

    async def presign_put(
        self, key: str, content_type: str, expires_in: int
    ) -> str:
        return f"mem://{key}?op=put&ct={content_type}&exp={expires_in}"


def test_fake_satisfies_protocol_runtime_check() -> None:
    assert isinstance(_FakeStore(), BlobStore)
