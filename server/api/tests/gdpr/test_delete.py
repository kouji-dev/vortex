"""N2 — GDPR data delete (Article 17) TDD.

Covers:
- ``register_deleter`` adds a module callable to the registry.
- Submit job → row in ``data_delete_jobs`` with ``status=queued``, scope_json.
- Run job: every registered deleter invoked with (org_id, scope) → rows gone.
- On success: status=succeeded + completed_at + audit event emitted.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401
import ai_portal.gdpr.model  # noqa: F401
from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'GdprD') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


# ── Registry ────────────────────────────────────────────────────────────────


def test_register_deleter_records_callable():
    from ai_portal.gdpr.registry import (
        clear_deleters,
        list_deleters,
        register_deleter,
    )

    clear_deleters()

    async def chat_del(org_id, scope):  # noqa: ARG001
        return None

    register_deleter("chat", chat_del)
    assert "chat" in list_deleters()
    clear_deleters()


# ── Submit ──────────────────────────────────────────────────────────────────


@requires_postgres
def test_submit_delete_job_persists_queued_row():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gdpr.delete_service import submit_delete

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gdpr-del-submit")
            db.commit()
            scope = {"subject": "org", "org_id": str(org_id)}
            job = submit_delete(db, org_id=org_id, scope=scope)
            assert job.id is not None
            assert job.status == "queued"
            assert job.scope_json == scope
            assert job.completed_at is None
    finally:
        db.rollback()
        db.close()


# ── Run job: deleters fire, rows gone, audit emitted ────────────────────────


@requires_postgres
def test_run_delete_job_invokes_all_deleters_and_emits_audit(monkeypatch):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gdpr.delete_service import submit_delete
    from ai_portal.gdpr.delete_worker import run_delete_job
    from ai_portal.gdpr.registry import clear_deleters, register_deleter

    clear_deleters()
    calls: list[tuple[str, uuid.UUID, dict]] = []

    async def chat_del(org_id, scope):
        calls.append(("chat", org_id, scope))

    async def kb_del(org_id, scope):
        calls.append(("kb", org_id, scope))

    register_deleter("chat", chat_del)
    register_deleter("knowledge_base", kb_del)

    audit_events: list[dict] = []

    def fake_emit_audit(**kwargs):
        audit_events.append(kwargs)
        return None

    # Patch the symbol used inside the worker.
    monkeypatch.setattr("ai_portal.gdpr.delete_worker.emit_audit", fake_emit_audit)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gdpr-del-run")
            db.commit()
            scope = {"subject": "org", "org_id": str(org_id)}
            job = submit_delete(db, org_id=org_id, scope=scope)
            job_id = job.id

        asyncio.run(run_delete_job(job_id=job_id))

        # Both deleters invoked with same org + scope.
        assert {c[0] for c in calls} == {"chat", "kb"}
        for _, org, sc in calls:
            assert org == org_id
            assert sc == scope

        # Job row updated. Reopen the session — the worker committed via a
        # separate SessionLocal so the original snapshot is stale.
        db.close()
        db = SessionLocal()
        with bypass_rls(db):
            from ai_portal.gdpr.model import DataDeleteJob

            row = db.get(DataDeleteJob, job_id)
            assert row.status == "succeeded"
            assert row.completed_at is not None

        # Audit event emitted with event_type=gdpr.delete.completed.
        assert len(audit_events) == 1
        ev = audit_events[0]
        assert ev["org_id"] == org_id
        assert ev["event_type"] == "gdpr.delete.completed"
        assert ev["resource"]["type"] == "data_delete_job"
    finally:
        clear_deleters()
        db.close()


@requires_postgres
def test_run_delete_job_marks_failed_when_deleter_raises(monkeypatch):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gdpr.delete_service import submit_delete
    from ai_portal.gdpr.delete_worker import run_delete_job
    from ai_portal.gdpr.registry import clear_deleters, register_deleter

    clear_deleters()

    async def boom(org_id, scope):  # noqa: ARG001
        raise RuntimeError("nope")

    register_deleter("chat", boom)
    monkeypatch.setattr("ai_portal.gdpr.delete_worker.emit_audit", lambda **_: None)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gdpr-del-fail")
            db.commit()
            job = submit_delete(db, org_id=org_id, scope={"subject": "org"})
            job_id = job.id

        asyncio.run(run_delete_job(job_id=job_id))

        db.close()
        db = SessionLocal()
        with bypass_rls(db):
            from ai_portal.gdpr.model import DataDeleteJob

            row = db.get(DataDeleteJob, job_id)
            assert row.status == "failed"
            assert row.completed_at is not None
    finally:
        clear_deleters()
        db.close()


# ── Router shape ────────────────────────────────────────────────────────────


def test_delete_router_exposes_paths():
    from ai_portal.gdpr.router import router

    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/v1/data-delete" in paths
    assert "/v1/data-delete/{job_id}" in paths


def test_delete_router_methods():
    from ai_portal.gdpr.router import router

    methods_by_path: dict[str, set[str]] = {}
    for r in router.routes:  # type: ignore[attr-defined]
        methods_by_path.setdefault(r.path, set()).update(r.methods or set())
    assert "POST" in methods_by_path["/v1/data-delete"]
    assert "GET" in methods_by_path["/v1/data-delete/{job_id}"]


# ── Facade re-export ────────────────────────────────────────────────────────


def test_control_plane_facade_exports_register_deleter():
    from ai_portal import control_plane

    assert hasattr(control_plane, "register_deleter")
