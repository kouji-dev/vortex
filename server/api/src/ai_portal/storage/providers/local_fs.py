"""Local-filesystem BlobStore — dev / tests only.

Stores blobs under ``<root>/<key>``. Presigned URLs are file:// URIs with a
query-string expiry — useful for tests that inspect the URL shape, **not**
safe for production access control. Never enable this in deployed envs.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from urllib.parse import quote

from ai_portal.storage.protocol import BlobNotFound


class LocalFsBlobStore:
    """Local filesystem BlobStore. Dev-only."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Normalise + sandbox: refuse anything escaping ``root``.
        candidate = (self.root / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"key escapes storage root: {key!r}") from exc
        return candidate

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        def _write() -> str:
            target = self._path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            # Sidecar content-type so ``get`` round-trips if needed later.
            (target.parent / f".{target.name}.ct").write_text(
                content_type, encoding="utf-8"
            )
            return target.as_uri()

        return await asyncio.to_thread(_write)

    async def get(self, key: str) -> bytes:
        def _read() -> bytes:
            target = self._path(key)
            if not target.is_file():
                raise BlobNotFound(key)
            return target.read_bytes()

        return await asyncio.to_thread(_read)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            target = self._path(key)
            if target.is_file():
                target.unlink()
            sidecar = target.parent / f".{target.name}.ct"
            if sidecar.is_file():
                sidecar.unlink()

        await asyncio.to_thread(_delete)

    async def presign_get(self, key: str, expires_in: int) -> str:
        target = self._path(key)
        expires_at = int(time.time()) + int(expires_in)
        return f"{target.as_uri()}?expires={expires_at}&op=get"

    async def presign_put(
        self, key: str, content_type: str, expires_in: int
    ) -> str:
        target = self._path(key)
        expires_at = int(time.time()) + int(expires_in)
        ct = quote(content_type, safe="")
        return (
            f"{target.as_uri()}?expires={expires_at}&op=put&content_type={ct}"
        )
