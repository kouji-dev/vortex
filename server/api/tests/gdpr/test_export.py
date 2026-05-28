"""N1 — GDPR data export (Article 15) TDD.

Covers:
- ``register_exporter`` adds a module callable to the global registry.
- Submitting a job persists ``data_export_jobs`` row with ``queued`` status.
- Running the job: iterates registered exporters → builds a zip in BlobStore
  → updates row ``status=succeeded`` + ``result_url`` → notifies requester.
- Two exporters fan out to two files inside the zip.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile

from sqlalchemy import text

# Force model imports so Base.metadata sees the tables.
import ai_portal.auth.model  # noqa: F401
import ai_portal.gdpr.model  # noqa: F401
from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'GdprX') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


# ── Registry ────────────────────────────────────────────────────────────────


def test_register_exporter_records_callable():
    from ai_portal.gdpr.registry import (
        clear_exporters,
        list_exporters,
        register_exporter,
    )

    clear_exporters()

    async def chat_export(org_id: uuid.UUID) -> dict:
        return {"threads": [{"id": "t1", "title": "hello"}]}

    register_exporter("chat", chat_export)
    assert "chat" in list_exporters()
    clear_exporters()


def test_register_exporter_overwrite_replaces():
    from ai_portal.gdpr.registry import (
        clear_exporters,
        get_exporter,
        register_exporter,
    )

    clear_exporters()

    async def a(_):
        return {"v": 1}

    async def b(_):
        return {"v": 2}

    register_exporter("chat", a)
    register_exporter("chat", b)
    assert get_exporter("chat") is b
    clear_exporters()


# ── Submit job ──────────────────────────────────────────────────────────────


@requires_postgres
def test_submit_export_job_persists_queued_row():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gdpr.export_service import submit_export

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gdpr-submit")
            db.commit()
            job = submit_export(db, org_id=org_id, requested_by=None)
            assert job.id is not None
            assert job.org_id == org_id
            assert job.status == "queued"
            assert job.result_url is None
            assert job.completed_at is None
    finally:
        db.rollback()
        db.close()


# ── Run job: zip + upload + notify ──────────────────────────────────────────


class _StubBlob:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = data
        return f"blob://{key}"

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def presign_get(self, key: str, expires_in: int) -> str:
        return f"https://signed/{key}?ttl={expires_in}"

    async def presign_put(self, key: str, content_type: str, expires_in: int) -> str:
        return f"https://signed-put/{key}?ttl={expires_in}"


class _StubNotify:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, dict]] = []

    async def send(
        self, *, channel: str, recipient: str, template_id: str, payload: dict
    ) -> None:
        self.calls.append((channel, recipient, template_id, payload))


@requires_postgres
def test_run_export_job_builds_zip_uploads_and_notifies():
    import asyncio

    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gdpr.export_service import submit_export
    from ai_portal.gdpr.export_worker import run_export_job
    from ai_portal.gdpr.registry import clear_exporters, register_exporter

    clear_exporters()

    async def chat_exporter(org_id: uuid.UUID) -> dict:
        return {"threads": [{"id": "t1", "title": "hi"}]}

    async def kb_exporter(org_id: uuid.UUID) -> dict:
        return {"knowledge_bases": [{"id": "kb1", "name": "Docs"}]}

    register_exporter("chat", chat_exporter)
    register_exporter("knowledge_base", kb_exporter)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gdpr-run")
            db.commit()
            job = submit_export(db, org_id=org_id, requested_by=None)
            job_id = job.id

        blob = _StubBlob()
        notify = _StubNotify()

        asyncio.run(
            run_export_job(
                job_id=job_id,
                blob_store=blob,
                notify=notify,
                notify_recipient="dpo@example.com",
            )
        )

        # Refetch job row in a fresh session — the worker committed via a
        # separate SessionLocal so this session's snapshot may be stale.
        db.close()
        db = SessionLocal()
        with bypass_rls(db):
            from ai_portal.gdpr.model import DataExportJob

            row = db.get(DataExportJob, job_id)
            assert row is not None
            assert row.status == "succeeded"
            assert row.result_url is not None
            assert row.completed_at is not None

        # Zip uploaded under a single key.
        assert len(blob.objects) == 1
        (zip_bytes,) = blob.objects.values()
        # Validate zip contents.
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = set(zf.namelist())
        assert "chat.json" in names
        assert "knowledge_base.json" in names
        assert json.loads(zf.read("chat.json")) == {
            "threads": [{"id": "t1", "title": "hi"}]
        }
        assert json.loads(zf.read("knowledge_base.json")) == {
            "knowledge_bases": [{"id": "kb1", "name": "Docs"}]
        }

        # Notification sent with presigned URL.
        assert len(notify.calls) == 1
        channel, recipient, template_id, payload = notify.calls[0]
        assert recipient == "dpo@example.com"
        assert template_id == "data_export_ready"
        assert payload["url"].startswith("https://signed/")
    finally:
        clear_exporters()
        db.close()


@requires_postgres
def test_run_export_with_no_exporters_still_produces_empty_zip():
    import asyncio

    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gdpr.export_service import submit_export
    from ai_portal.gdpr.export_worker import run_export_job
    from ai_portal.gdpr.registry import clear_exporters

    clear_exporters()
    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gdpr-empty")
            db.commit()
            job = submit_export(db, org_id=org_id, requested_by=None)
            job_id = job.id

        blob = _StubBlob()
        notify = _StubNotify()
        asyncio.run(
            run_export_job(
                job_id=job_id,
                blob_store=blob,
                notify=notify,
                notify_recipient=None,
            )
        )
        db.close()
        db = SessionLocal()
        with bypass_rls(db):
            from ai_portal.gdpr.model import DataExportJob

            row = db.get(DataExportJob, job_id)
            assert row.status == "succeeded"
        # No notify recipient → no send.
        assert notify.calls == []
        # Zip still uploaded (empty payload).
        assert len(blob.objects) == 1
    finally:
        clear_exporters()
        db.close()


# ── Router shape ────────────────────────────────────────────────────────────


def test_export_router_exposes_paths():
    from ai_portal.gdpr.router import router

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/v1/data-export" in paths
    assert "/v1/data-export/{job_id}" in paths


def test_export_router_methods():
    from ai_portal.gdpr.router import router

    methods_by_path: dict[str, set[str]] = {}
    for r in router.routes:  # type: ignore[attr-defined]
        methods_by_path.setdefault(r.path, set()).update(r.methods or set())
    assert "POST" in methods_by_path["/v1/data-export"]
    assert "GET" in methods_by_path["/v1/data-export/{job_id}"]


# ── Facade re-export ────────────────────────────────────────────────────────


def test_control_plane_facade_exports_register_exporter():
    from ai_portal import control_plane

    assert hasattr(control_plane, "register_exporter")
