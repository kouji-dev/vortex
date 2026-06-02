"""Tests: usable_in_worker field + ?usable_in_worker filter on GET /api/models."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_portal.catalog.schemas import CatalogModelRead
from ai_portal.catalog.model_settings import model_settings_from_metadata
from ai_portal.main import app
from tests.conftest import requires_postgres

client = TestClient(app)
AUTH = {"Authorization": "Bearer devtoken"}


# ---------------------------------------------------------------------------
# Unit-level: schema field exists and defaults False
# ---------------------------------------------------------------------------

def test_catalog_model_read_has_usable_in_worker_field():
    """CatalogModelRead must expose usable_in_worker and default it to False."""
    row = CatalogModelRead(
        id=1,
        slug="test-slug",
        display_name="Test",
        description="desc",
        api_model_id="test-model",
        effort="default",
        sort_order=0,
        catalog_metadata=None,
        model_settings=model_settings_from_metadata(None),
        accessible=True,
        can_request_access=False,
        request_access_url=None,
        is_default=False,
    )
    assert hasattr(row, "usable_in_worker")
    assert row.usable_in_worker is False


def test_catalog_model_read_usable_in_worker_explicit_true():
    """CatalogModelRead accepts usable_in_worker=True."""
    row = CatalogModelRead(
        id=2,
        slug="worker-slug",
        display_name="Worker Model",
        description="desc",
        api_model_id="claude-test",
        effort="high",
        sort_order=1,
        catalog_metadata=None,
        model_settings=model_settings_from_metadata(None),
        accessible=True,
        usable_in_worker=True,
        can_request_access=False,
        request_access_url=None,
        is_default=False,
    )
    assert row.usable_in_worker is True


# ---------------------------------------------------------------------------
# Integration-level: endpoint shape + filter (requires live Postgres + seed)
# ---------------------------------------------------------------------------

@requires_postgres
def test_list_models_includes_usable_in_worker_key(monkeypatch):
    """Every row returned by GET /api/models must include usable_in_worker."""
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "test-pepper")

    r = client.get("/api/models", headers=AUTH)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) > 0, "expected at least one catalog model in seed DB"
    assert all("usable_in_worker" in row for row in data), (
        "usable_in_worker key missing from one or more rows"
    )


@requires_postgres
def test_list_models_worker_filter_returns_subset(monkeypatch):
    """?usable_in_worker=true returns only flagged rows, fewer than unfiltered."""
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "test-pepper")

    all_r = client.get("/api/models", headers=AUTH)
    assert all_r.status_code == 200, all_r.text
    all_data = all_r.json()

    worker_r = client.get("/api/models?usable_in_worker=true", headers=AUTH)
    assert worker_r.status_code == 200, worker_r.text
    worker_data = worker_r.json()

    # All returned rows must have usable_in_worker=True
    assert all(row["usable_in_worker"] is True for row in worker_data), (
        "filtered endpoint returned a row with usable_in_worker=false"
    )

    # Migration 073 marks claude-* and %codex% rows as True; there should be
    # at least one such row in the seed DB.
    assert len(worker_data) >= 1, "expected at least one worker-flagged model"

    # Filtered set must be smaller than the full set (seed contains gemini-* rows
    # which are not flagged).
    assert len(worker_data) < len(all_data), (
        f"worker filter did not reduce the set "
        f"({len(worker_data)} vs {len(all_data)} unfiltered)"
    )


@requires_postgres
def test_list_models_worker_filter_false_returns_non_worker(monkeypatch):
    """?usable_in_worker=false returns only non-flagged rows."""
    monkeypatch.setenv("PORTAL_API_KEY_PEPPER", "test-pepper")

    r = client.get("/api/models?usable_in_worker=false", headers=AUTH)
    assert r.status_code == 200, r.text
    data = r.json()

    assert all(row["usable_in_worker"] is False for row in data), (
        "non-worker filter returned a row with usable_in_worker=true"
    )
