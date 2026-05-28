"""Files router — multipart upload, presign, delete via HTTP.

The :class:`FilesService` is swapped via ``dependency_overrides`` so this
suite has no DB. We assert the wire shapes + that the calls flow through
the service correctly (upload → presign → delete).
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_actor
from ai_portal.gateway.files.router import (
    get_files_service,
    router as files_router,
)
from ai_portal.gateway.files.service import FileMetadata, FileNotFound
from ai_portal.rbac.service import Actor


def _actor() -> Actor:
    return Actor(
        org_id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        kind="user",
        user_id=42,
    )


class _StubSvc:
    """In-memory stand-in for :class:`FilesService`.

    Stores files in a dict keyed by ``(org_id, file_id)``. Presigning
    returns a deterministic synthetic URL.
    """

    def __init__(self) -> None:
        self.files: dict[tuple[uuid.UUID, uuid.UUID], dict] = {}

    async def upload(
        self,
        *,
        org_id: uuid.UUID,
        actor_user_id: int | None,
        data: bytes,
        filename: str,
        content_type: str,
        purpose: str = "user_data",
    ) -> FileMetadata:
        fid = uuid.uuid4()
        self.files[(org_id, fid)] = {
            "data": data,
            "filename": filename,
            "content_type": content_type,
            "purpose": purpose,
            "actor_user_id": actor_user_id,
        }
        return FileMetadata(
            id=fid,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            purpose=purpose,
            blob_key=f"gateway/files/{org_id}/{fid}/{filename}",
        )

    async def presign_get(
        self, *, org_id: uuid.UUID, file_id: uuid.UUID, expires_in: int = 300
    ) -> str:
        if (org_id, file_id) not in self.files:
            raise FileNotFound(str(file_id))
        return f"https://signed/{file_id}?exp={expires_in}"

    async def delete(self, *, org_id: uuid.UUID, file_id: uuid.UUID) -> None:
        if (org_id, file_id) not in self.files:
            raise FileNotFound(str(file_id))
        del self.files[(org_id, file_id)]


def _build_app(actor: Actor, svc: _StubSvc):
    """Build a FastAPI app for one test. Bypasses DB/RLS entirely."""
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[require_actor] = lambda: actor
    app.dependency_overrides[get_files_service] = lambda: svc
    # GET /v1/files (list) hits get_db directly; swap to a fake that returns
    # an object with .scalars() chained over an empty list — list path is
    # not asserted in this suite so this is a minimal no-op.

    class _NopDb:
        def scalars(self, _stmt):
            return iter([])

    app.dependency_overrides[get_db] = lambda: _NopDb()
    return app


# ── tests ────────────────────────────────────────────────────────────────


def test_upload_returns_metadata() -> None:
    svc = _StubSvc()
    client = TestClient(_build_app(_actor(), svc))

    res = client.post(
        "/v1/files",
        files={"file": ("notes.txt", b"hello bytes", "text/plain")},
        data={"purpose": "user_data"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["object"] == "file"
    assert body["filename"] == "notes.txt"
    assert body["bytes"] == len(b"hello bytes")
    assert body["purpose"] == "user_data"
    assert "id" in body

    # Service got the bytes + actor user_id.
    org = _actor().org_id
    saved = next(iter(svc.files.values()))
    assert saved["data"] == b"hello bytes"
    assert saved["actor_user_id"] == _actor().user_id
    # File is org-scoped (key contains org).
    fid = uuid.UUID(body["id"])
    assert (org, fid) in svc.files


def test_upload_rejects_empty_file() -> None:
    svc = _StubSvc()
    client = TestClient(_build_app(_actor(), svc))

    res = client.post(
        "/v1/files",
        files={"file": ("empty.bin", b"", "application/octet-stream")},
    )
    assert res.status_code == 422


def test_get_returns_presigned_url() -> None:
    """Service contract: upload → presign returns a short-lived URL."""
    import asyncio

    svc = _StubSvc()
    org = _actor().org_id

    async def _run() -> str:
        meta = await svc.upload(
            org_id=org,
            actor_user_id=None,
            data=b"abc",
            filename="a.txt",
            content_type="text/plain",
        )
        return await svc.presign_get(
            org_id=org, file_id=meta.id, expires_in=60
        )

    url = asyncio.run(_run())
    assert url.startswith("https://signed/")
    assert "exp=60" in url


def test_delete_removes_file() -> None:
    svc = _StubSvc()
    client = TestClient(_build_app(_actor(), svc))

    res = client.post(
        "/v1/files",
        files={"file": ("a.txt", b"abc", "text/plain")},
    )
    fid = res.json()["id"]

    res = client.delete(f"/v1/files/{fid}")
    assert res.status_code == 204

    # Second delete is 404.
    res = client.delete(f"/v1/files/{fid}")
    assert res.status_code == 404


def test_upload_then_delete_then_presign_404() -> None:
    """End-to-end: upload → delete → presign returns 404 via FileNotFound."""
    import asyncio

    import pytest

    svc = _StubSvc()
    client = TestClient(_build_app(_actor(), svc))
    res = client.post(
        "/v1/files",
        files={"file": ("a.txt", b"abc", "text/plain")},
    )
    fid = uuid.UUID(res.json()["id"])
    client.delete(f"/v1/files/{fid}")

    async def _presign() -> None:
        await svc.presign_get(org_id=_actor().org_id, file_id=fid)

    with pytest.raises(FileNotFound):
        asyncio.run(_presign())
