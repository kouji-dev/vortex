"""Tests for :class:`AzureBlobStore`.

The Azure SDK has no first-class moto equivalent; we patch
``BlobServiceClient.get_blob_client`` and ``generate_blob_sas`` so the
provider is exercised without a real account.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import patch

import pytest
from azure.core.exceptions import ResourceNotFoundError

from ai_portal.storage.protocol import BlobNotFound
from ai_portal.storage.providers import azure_blob as az
from ai_portal.storage.providers.azure_blob import AzureBlobStore

CONNECTION_STRING = (
    "DefaultEndpointsProtocol=https;"
    "AccountName=devacct;"
    "AccountKey="
    + base64.b64encode(b"unit-test-key").decode("ascii")
    + ";"
    "EndpointSuffix=core.windows.net"
)
CONTAINER = "blobs"


class _FakeBlobClient:
    def __init__(self, store: dict[str, tuple[bytes, str]], key: str) -> None:
        self._store = store
        self._key = key
        self.url = f"https://devacct.blob.core.windows.net/{CONTAINER}/{key}"

    def upload_blob(
        self,
        data: bytes,
        *,
        overwrite: bool = False,
        content_settings: Any | None = None,
    ) -> None:
        if not overwrite and self._key in self._store:
            raise RuntimeError("blob exists; overwrite=False")
        ct = (
            content_settings.content_type
            if content_settings is not None
            else "application/octet-stream"
        )
        self._store[self._key] = (data, ct)

    def download_blob(self) -> _FakeDownloader:
        if self._key not in self._store:
            raise ResourceNotFoundError(message="blob not found")
        return _FakeDownloader(self._store[self._key][0])

    def delete_blob(self) -> None:
        if self._key not in self._store:
            raise ResourceNotFoundError(message="blob not found")
        del self._store[self._key]


class _FakeDownloader:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


@pytest.fixture
def fake_backend() -> dict[str, tuple[bytes, str]]:
    return {}


@pytest.fixture
def azure_store(
    fake_backend: dict[str, tuple[bytes, str]],
    monkeypatch: pytest.MonkeyPatch,
):  # type: ignore[no-untyped-def]
    class _FakeServiceClient:
        @classmethod
        def from_connection_string(cls, _cs: str) -> _FakeServiceClient:
            return cls()

        def get_blob_client(
            self, *, container: str, blob: str
        ) -> _FakeBlobClient:
            assert container == CONTAINER
            return _FakeBlobClient(fake_backend, blob)

    monkeypatch.setattr(az, "BlobServiceClient", _FakeServiceClient)
    # Avoid hitting real SAS signing — return a deterministic token.
    monkeypatch.setattr(
        az,
        "generate_blob_sas",
        lambda **kwargs: (
            "sv=2024-01-01&sig=fake"
            f"&perms={'rw' if kwargs['permission'].write else 'r'}"
        ),
    )
    return AzureBlobStore(CONTAINER, connection_string=CONNECTION_STRING)


def test_constructor_requires_credentials() -> None:
    with pytest.raises(ValueError):
        AzureBlobStore(CONTAINER)


@pytest.mark.asyncio
async def test_put_returns_blob_url(azure_store: AzureBlobStore) -> None:
    url = await azure_store.put("a/b.bin", b"hi", "application/octet-stream")
    assert url.startswith("https://devacct.blob.core.windows.net/")
    assert "a/b.bin" in url


@pytest.mark.asyncio
async def test_put_get_roundtrip(
    azure_store: AzureBlobStore,
    fake_backend: dict[str, tuple[bytes, str]],
) -> None:
    await azure_store.put("k", b"payload", "text/plain")
    assert fake_backend["k"] == (b"payload", "text/plain")
    assert await azure_store.get("k") == b"payload"


@pytest.mark.asyncio
async def test_get_missing_raises(azure_store: AzureBlobStore) -> None:
    with pytest.raises(BlobNotFound):
        await azure_store.get("nope")


@pytest.mark.asyncio
async def test_delete_idempotent(azure_store: AzureBlobStore) -> None:
    await azure_store.delete("missing")  # no raise
    await azure_store.put("k", b"v", "text/plain")
    await azure_store.delete("k")
    await azure_store.delete("k")  # second delete: no raise
    with pytest.raises(BlobNotFound):
        await azure_store.get("k")


@pytest.mark.asyncio
async def test_presign_get_appends_sas(azure_store: AzureBlobStore) -> None:
    url = await azure_store.presign_get("k", 300)
    assert "sig=fake" in url
    assert "perms=r" in url


@pytest.mark.asyncio
async def test_presign_put_uses_write_perms(
    azure_store: AzureBlobStore,
) -> None:
    url = await azure_store.presign_put("k", "image/png", 300)
    assert "perms=rw" in url


def test_connection_string_credentials_parsed() -> None:
    store = AzureBlobStore(CONTAINER, connection_string=CONNECTION_STRING)
    name, key = store._resolve_credentials()
    assert name == "devacct"
    assert key == base64.b64encode(b"unit-test-key").decode("ascii")


def test_account_url_only_blocks_sas() -> None:
    store = AzureBlobStore(
        CONTAINER, account_url="https://devacct.blob.core.windows.net"
    )
    with pytest.raises(RuntimeError):
        store._resolve_credentials()


@pytest.mark.asyncio
async def test_real_sas_signing_smoke() -> None:
    """End-to-end SAS generation using the real ``generate_blob_sas``.

    Confirms we pass the SDK the right kwargs — exercises the un-patched
    code path. No network is hit; signing is local.
    """
    with patch.object(az, "BlobServiceClient") as svc_cls:
        svc_cls.from_connection_string.return_value.get_blob_client.return_value = _FakeBlobClient(  # noqa: E501
            {}, "k"
        )
        store = AzureBlobStore(
            CONTAINER, connection_string=CONNECTION_STRING
        )
        url = await store.presign_get("k", 60)
        assert "sig=" in url
        assert "se=" in url  # SAS expiry parameter
