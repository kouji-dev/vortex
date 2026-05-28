"""Files service unit tests — upload → presign_get → delete roundtrip.

Uses a tempdir-backed :class:`LocalFsBlobStore` and an in-memory fake
session that records ``add``/``delete``/``commit`` calls. The service is
the only thing under test here; the alembic migration + RLS policy are
covered by the gateway DB integration suite.
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_portal.gateway.files.model import GatewayFile
from ai_portal.gateway.files.service import FileNotFound, FilesService
from ai_portal.storage.providers.local_fs import LocalFsBlobStore


# ── fake session ─────────────────────────────────────────────────────────


class _FakeSession:
    """In-memory stand-in for :class:`sqlalchemy.orm.Session`.

    Only the methods :class:`FilesService` uses are implemented.
    """

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, GatewayFile] = {}
        self.commits = 0

    def add(self, obj: GatewayFile) -> None:
        # Backfill created_at since the DB default isn't running here.
        if obj.created_at is None:
            object.__setattr__(obj, "created_at", datetime.now(UTC))
        self.rows[obj.id] = obj

    def delete(self, obj: GatewayFile) -> None:
        self.rows.pop(obj.id, None)

    def flush(self) -> None:  # noqa: D401
        return None

    def commit(self) -> None:
        self.commits += 1

    def scalar(self, stmt):  # noqa: ANN001
        # We simulate the two filters used: id + org_id.
        # Read the where clauses via the ORM compile description.
        # Easier: linear scan with the captured criteria below.
        criteria = getattr(stmt, "_test_criteria", None)
        if criteria is None:
            # Pull from the where clauses we know the service uses.
            for row in self.rows.values():
                if (
                    row.id == self._last_query_id
                    and row.org_id == self._last_query_org
                ):
                    return row
            return None
        return None

    # The service uses `select(GatewayFile).where(id == ..., org_id == ...)`.
    # We can't introspect the BinaryExpressions cheaply, so we intercept
    # by patching the service's _fetch in tests.


# Helper — bypass scalar() by patching `_fetch` directly.
def _bind_fetch(svc: FilesService, sess: _FakeSession) -> None:
    def _fetch(*, org_id: uuid.UUID, file_id: uuid.UUID) -> GatewayFile:
        row = sess.rows.get(file_id)
        if row is None or row.org_id != org_id:
            raise FileNotFound(str(file_id))
        return row

    svc._fetch = _fetch  # type: ignore[method-assign]


# ── tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_persists_metadata_and_writes_blob() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = LocalFsBlobStore(td)
        sess = _FakeSession()
        svc = FilesService(db=sess, blob_store=store)  # type: ignore[arg-type]
        _bind_fetch(svc, sess)

        org = uuid.uuid4()
        meta = await svc.upload(
            org_id=org,
            actor_user_id=7,
            data=b"hello bytes",
            filename="notes.txt",
            content_type="text/plain",
        )

        assert meta.filename == "notes.txt"
        assert meta.content_type == "text/plain"
        assert meta.size_bytes == len(b"hello bytes")
        assert meta.purpose == "user_data"

        # Metadata row exists and is org-scoped.
        row = sess.rows[meta.id]
        assert row.org_id == org
        assert row.actor_user_id == 7
        assert row.blob_key.startswith(f"gateway/files/{org}/{meta.id}/")
        assert sess.commits == 1

        # Bytes round-trip via the blob store.
        on_disk = Path(td) / row.blob_key
        assert on_disk.read_bytes() == b"hello bytes"


@pytest.mark.asyncio
async def test_presign_get_returns_url_for_owner_only() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = LocalFsBlobStore(td)
        sess = _FakeSession()
        svc = FilesService(db=sess, blob_store=store)  # type: ignore[arg-type]
        _bind_fetch(svc, sess)

        org = uuid.uuid4()
        other_org = uuid.uuid4()
        meta = await svc.upload(
            org_id=org,
            actor_user_id=None,
            data=b"abc",
            filename="x.bin",
            content_type="application/octet-stream",
        )

        url = await svc.presign_get(org_id=org, file_id=meta.id, expires_in=60)
        assert "file://" in url or url.startswith("file:")
        assert "expires=" in url
        assert "op=get" in url

        # Cross-org presign refuses to leak the URL.
        with pytest.raises(FileNotFound):
            await svc.presign_get(
                org_id=other_org, file_id=meta.id, expires_in=60
            )


@pytest.mark.asyncio
async def test_delete_removes_blob_and_row() -> None:
    with tempfile.TemporaryDirectory() as td:
        store = LocalFsBlobStore(td)
        sess = _FakeSession()
        svc = FilesService(db=sess, blob_store=store)  # type: ignore[arg-type]
        _bind_fetch(svc, sess)

        org = uuid.uuid4()
        meta = await svc.upload(
            org_id=org,
            actor_user_id=None,
            data=b"xyz",
            filename="y.bin",
            content_type="application/octet-stream",
        )
        blob_path = Path(td) / sess.rows[meta.id].blob_key
        assert blob_path.exists()

        await svc.delete(org_id=org, file_id=meta.id)

        # Row gone, bytes gone, idempotent missing-key delete OK.
        assert meta.id not in sess.rows
        assert not blob_path.exists()
        with pytest.raises(FileNotFound):
            await svc.delete(org_id=org, file_id=meta.id)
