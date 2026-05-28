"""File-scoped tests for the SinkMetrics tracker + observability endpoints."""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_metrics():
    from ai_portal.audit.sinks_metrics import metrics

    metrics().reset()
    yield
    metrics().reset()


# ---- metric primitive ----------------------------------------------------


def test_record_success_and_error():
    from ai_portal.audit.sinks_metrics import metrics

    m = metrics()
    org = uuid.uuid4()
    m.record_success(org, "splunk_hec", 12.5)
    m.record_success(org, "splunk_hec", 17.0)
    m.record_error(org, "splunk_hec", RuntimeError("boom"))

    rows = m.list_org(org)
    assert len(rows) == 1
    row = rows[0]
    assert row["sink"] == "splunk_hec"
    assert row["samples"] == 3
    assert row["success_count"] == 2
    assert row["error_count"] == 1
    assert 0.0 < row["success_rate"] < 1.0
    assert row["last_status"] == "error"
    assert "boom" in row["last_error"]
    assert row["p50_latency_ms"] is not None
    assert row["p95_latency_ms"] is not None


def test_org_isolation():
    from ai_portal.audit.sinks_metrics import metrics

    a, b = uuid.uuid4(), uuid.uuid4()
    metrics().record_success(a, "sink_a", 1.0)
    metrics().record_success(b, "sink_b", 1.0)
    assert [r["sink"] for r in metrics().list_org(a)] == ["sink_a"]
    assert [r["sink"] for r in metrics().list_org(b)] == ["sink_b"]


def test_record_write_helper():
    from ai_portal.audit.sinks_metrics import metrics, record_write

    org = uuid.uuid4()
    started = time.perf_counter() - 0.01  # ~10 ms ago
    record_write(org, "splunk_hec", started_at=started, error=None)
    rows = metrics().list_org(org)
    assert rows[0]["samples"] == 1
    assert rows[0]["p50_latency_ms"] >= 0.0


# ---- endpoint smoke ------------------------------------------------------


def _user_with_org(role: str = "admin", org_id=None):
    from ai_portal.auth.model import User

    u = User(
        id=1,
        email="admin@example.com",
        is_active=True,
        is_verified=True,
        role=role,
        org_id=org_id or uuid.uuid4(),
    )
    return u


def _make_app() -> tuple[FastAPI, "User"]:  # type: ignore[name-defined]
    from ai_portal.audit.sinks_router import _require_admin, router
    from ai_portal.auth.deps import get_current_user

    app = FastAPI()
    user = _user_with_org()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[_require_admin] = lambda: user
    app.include_router(router)
    return app, user


def test_health_endpoint_returns_per_sink_rows():
    from ai_portal.audit.sinks_metrics import metrics

    app, user = _make_app()
    metrics().record_success(user.org_id, "splunk_hec", 7.0)
    metrics().record_error(user.org_id, "datadog_logs", "down")

    r = TestClient(app).get("/v1/audit/sinks/health")
    assert r.status_code == 200
    body = r.json()
    assert body["org_id"] == str(user.org_id)
    names = {row["sink"] for row in body["items"]}
    assert names == {"splunk_hec", "datadog_logs"}
    for row in body["items"]:
        if row["sink"] == "datadog_logs":
            assert row["last_status"] == "error"
            assert "down" in row["last_error"]


def test_metrics_endpoint_returns_latency_and_rates():
    from ai_portal.audit.sinks_metrics import metrics

    app, user = _make_app()
    for v in (1.0, 2.0, 3.0, 4.0, 5.0):
        metrics().record_success(user.org_id, "splunk_hec", v)

    r = TestClient(app).get("/v1/audit/sinks/metrics")
    assert r.status_code == 200
    body = r.json()
    row = body["items"][0]
    assert row["samples"] == 5
    assert row["success_rate"] == 1.0
    assert row["p50_latency_ms"] == 3.0
    assert row["p95_latency_ms"] >= 4.0


def test_endpoints_403_without_org():
    from ai_portal.audit.sinks_router import _require_admin, router
    from ai_portal.auth.deps import get_current_user

    app = FastAPI()
    user = _user_with_org()
    user.org_id = None  # type: ignore[assignment]
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[_require_admin] = lambda: user
    app.include_router(router)

    c = TestClient(app)
    assert c.get("/v1/audit/sinks/health").status_code == 403
    assert c.get("/v1/audit/sinks/metrics").status_code == 403
