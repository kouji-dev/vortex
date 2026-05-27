"""Azure Blob Storage BlobStore.

Uses ``azure-storage-blob`` synchronously, dispatched via
``asyncio.to_thread``. Presigned URLs are SAS tokens. Connection details
come from either a connection string or (account name + key).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from ai_portal.storage.protocol import BlobNotFound


class AzureBlobStore:
    """Azure Blob Storage-backed BlobStore."""

    def __init__(
        self,
        container: str,
        *,
        connection_string: str | None = None,
        account_url: str | None = None,
        account_name: str | None = None,
        account_key: str | None = None,
    ) -> None:
        if connection_string is None and account_url is None:
            raise ValueError(
                "AzureBlobStore needs connection_string or account_url"
            )
        self.container = container
        self._connection_string = connection_string
        self._account_url = account_url
        self._account_name = account_name
        self._account_key = account_key

    def _service(self) -> BlobServiceClient:
        if self._connection_string is not None:
            return BlobServiceClient.from_connection_string(
                self._connection_string
            )
        return BlobServiceClient(
            account_url=self._account_url,  # type: ignore[arg-type]
            credential=self._account_key,
        )

    def _blob_client(self, key: str):  # type: ignore[no-untyped-def]
        return self._service().get_blob_client(
            container=self.container, blob=key
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        def _put() -> str:
            client = self._blob_client(key)
            client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            return client.url

        return await asyncio.to_thread(_put)

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                downloader = self._blob_client(key).download_blob()
            except ResourceNotFoundError as exc:
                raise BlobNotFound(key) from exc
            return downloader.readall()

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            try:
                self._blob_client(key).delete_blob()
            except ResourceNotFoundError:
                return

        await asyncio.to_thread(_delete)

    def _resolve_credentials(self) -> tuple[str, str]:
        if self._account_name is not None and self._account_key is not None:
            return self._account_name, self._account_key
        # Parse account name + key out of a connection string.
        if self._connection_string is None:
            raise RuntimeError(
                "SAS signing needs account_name+account_key or "
                "a connection_string carrying them"
            )
        parts = dict(
            item.split("=", 1)
            for item in self._connection_string.split(";")
            if "=" in item
        )
        name = parts.get("AccountName")
        key = parts.get("AccountKey")
        if not name or not key:
            raise RuntimeError(
                "connection_string missing AccountName/AccountKey"
            )
        return name, key

    def _sign(self, key: str, expires_in: int, *, write: bool) -> str:
        account_name, account_key = self._resolve_credentials()
        perms = (
            BlobSasPermissions(write=True, create=True)
            if write
            else BlobSasPermissions(read=True)
        )
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=self.container,
            blob_name=key,
            account_key=account_key,
            permission=perms,
            expiry=datetime.now(UTC) + timedelta(seconds=expires_in),
        )
        return f"{self._blob_client(key).url}?{sas}"

    async def presign_get(self, key: str, expires_in: int) -> str:
        return await asyncio.to_thread(
            self._sign, key, expires_in, write=False
        )

    async def presign_put(
        self, key: str, content_type: str, expires_in: int
    ) -> str:
        # content_type is part of the upload request the client makes; the
        # SAS itself does not bind it.
        del content_type
        return await asyncio.to_thread(
            self._sign, key, expires_in, write=True
        )
