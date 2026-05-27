"""Tests for :class:`LocalFsBlobStore`."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_portal.storage.protocol import BlobNotFound
from ai_portal.storage.providers.local_fs import LocalFsBlobStore


@pytest.mark.asyncio
async def test_put_writes_file_under_root(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    url = await store.put("docs/hello.txt", b"hi", "text/plain")
    target = tmp_path / "docs" / "hello.txt"
    assert target.read_bytes() == b"hi"
    assert url.startswith("file:")


@pytest.mark.asyncio
async def test_put_persists_content_type_sidecar(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    await store.put("a.json", b"{}", "application/json")
    sidecar = tmp_path / ".a.json.ct"
    assert sidecar.read_text(encoding="utf-8") == "application/json"


@pytest.mark.asyncio
async def test_get_roundtrip(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    await store.put("k", b"v" * 1024, "application/octet-stream")
    assert await store.get("k") == b"v" * 1024


@pytest.mark.asyncio
async def test_get_missing_raises(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    with pytest.raises(BlobNotFound):
        await store.get("nope")


@pytest.mark.asyncio
async def test_delete_idempotent(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    await store.delete("missing")
    await store.put("k", b"v", "text/plain")
    await store.delete("k")
    await store.delete("k")
    with pytest.raises(BlobNotFound):
        await store.get("k")


@pytest.mark.asyncio
async def test_delete_removes_sidecar(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    await store.put("file", b"d", "text/plain")
    assert (tmp_path / ".file.ct").exists()
    await store.delete("file")
    assert not (tmp_path / ".file.ct").exists()


@pytest.mark.asyncio
async def test_presign_get_encodes_expiry(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    await store.put("k", b"v", "text/plain")
    url = await store.presign_get("k", 3600)
    assert "op=get" in url
    assert "expires=" in url


@pytest.mark.asyncio
async def test_presign_put_encodes_content_type(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    url = await store.presign_put("k", "image/png", 60)
    assert "op=put" in url
    assert "image%2Fpng" in url


@pytest.mark.asyncio
async def test_key_escaping_root_rejected(tmp_path: Path) -> None:
    store = LocalFsBlobStore(tmp_path)
    with pytest.raises(ValueError):
        await store.put("../escape.txt", b"x", "text/plain")


def test_root_is_created(tmp_path: Path) -> None:
    LocalFsBlobStore(tmp_path / "nested" / "deeper")
    assert (tmp_path / "nested" / "deeper").is_dir()
