"""Smoke tests for kb_connectors / kb_sync_runs / kb_sync_errors models.

These tests do not hit the database — they verify:
- imports resolve without side effects
- expected columns exist
- the alembic revision chains off ``055_gateway_playground_evals``
"""

from __future__ import annotations

import importlib


def test_models_import_and_expose_expected_columns():
    mod = importlib.import_module("ai_portal.rag.connectors.model")
    KbConnector = mod.KbConnector
    KbSyncRun = mod.KbSyncRun
    KbSyncError = mod.KbSyncError

    cc = {c.name for c in KbConnector.__table__.columns}
    assert {
        "id",
        "kb_id",
        "kind",
        "name",
        "config_encrypted",
        "schedule_cron",
        "last_sync_at",
        "last_cursor",
        "enabled",
        "created_at",
        "updated_at",
    } <= cc

    rc = {c.name for c in KbSyncRun.__table__.columns}
    assert {
        "id",
        "connector_id",
        "started_at",
        "ended_at",
        "status",
        "docs_added",
        "docs_updated",
        "docs_deleted",
        "errors_count",
        "cursor_after",
    } <= rc

    ec = {c.name for c in KbSyncError.__table__.columns}
    assert {"id", "run_id", "source_uri", "error", "created_at"} <= ec


def test_alembic_revision_chained_off_055():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "056_rag_connectors.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_056", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "056_rag_connectors"
    assert mod.down_revision == "055_gateway_playground_evals"
