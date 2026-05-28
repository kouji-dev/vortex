"""Webhook router tests with fake payloads + stubbed deps."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.auth.deps import get_db
from ai_portal.workers.issues import registry as issues_registry
from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent
from ai_portal.workers.triggers.webhook_router import router as wh_router


class _FakeTracker:
    """Minimal tracker that returns whatever we tell it to."""

    def __init__(self, name: str, ev: IssueWebhookEvent | None) -> None:
        self.name = name
        self._ev = ev

    def parse_webhook_event(self, payload, headers):
        return self._ev


class _FakeIntegration:
    def __init__(self, mapping: dict) -> None:
        self.project_mapping_json = mapping


class _FakeQuery:
    def __init__(self, integ) -> None:
        self._integ = integ

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._integ


class _FakeDb:
    def __init__(self, integ, capture_submit: dict) -> None:
        self._integ = integ
        self._capture = capture_submit
        self.added: list = []

    def query(self, *a, **kw):
        return _FakeQuery(self._integ)

    def execute(self, *a, **kw):
        class _R:
            def scalar_one_or_none(self):
                return None

            def scalars(self):
                class _S:
                    def all(self):
                        return []

                return _S()

        return _R()

    def add(self, row):
        self.added.append(row)
        if not hasattr(row, "id"):
            row.id = uuid.uuid4()

    def flush(self):
        pass

    def commit(self):
        self._capture["committed"] = True


@pytest.fixture
def app_with_router():
    app = FastAPI()
    app.include_router(wh_router)
    return app


def _ev(*, kind: str, labels: list[str], external_id: str = "PROJ-1") -> IssueWebhookEvent:
    return IssueWebhookEvent(
        kind=kind,
        issue=Issue(
            id="1",
            external_id=external_id,
            title="Fix it",
            body="repro",
            url="https://example.com/i",
            labels=labels,
            status="open",
            repo_hint=None,
        ),
        actor="alice",
        raw={},
    )


def _setup(app, *, ev, mapping, pool_resolves: bool = True):
    """Wire stubs onto the app."""
    integ = _FakeIntegration(mapping)
    capture: dict = {}
    db = _FakeDb(integ, capture)

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db

    # Replace tracker for this test.
    issues_registry.clear()
    issues_registry.register(_FakeTracker(name="jira_cloud", ev=ev))

    # Monkey-patch svc.submit_task to skip real DB writes.
    from ai_portal.workers import service as svc

    def _fake_submit(db, **kw):
        capture["kw"] = kw

        class _T:
            id = uuid.uuid4()

        return _T()

    svc.submit_task_original = getattr(svc, "submit_task")
    svc.submit_task = _fake_submit  # type: ignore[assignment]
    return capture


def _teardown(app):
    app.dependency_overrides.clear()
    from ai_portal.workers import service as svc

    if hasattr(svc, "submit_task_original"):
        svc.submit_task = svc.submit_task_original  # type: ignore[assignment]
    issues_registry.clear()


def test_unknown_provider_404(app_with_router) -> None:
    client = TestClient(app_with_router)
    r = client.post(
        "/v1/workers/webhooks/unknown",
        json={},
        headers={"X-Org-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


def test_missing_org_header_400(app_with_router) -> None:
    client = TestClient(app_with_router)
    r = client.post("/v1/workers/webhooks/jira_cloud", json={})
    assert r.status_code == 400


def test_jira_webhook_submits_on_label_match(app_with_router) -> None:
    ev = _ev(kind="labeled", labels=["ai-worker"], external_id="PROJ-1")
    mapping = {
        "PROJ": {
            "pool_id": str(uuid.uuid4()),
            "trigger_label": "ai-worker",
            "repo": "acme/api",
        }
    }
    capture = _setup(app_with_router, ev=ev, mapping=mapping)
    try:
        client = TestClient(app_with_router)
        r = client.post(
            "/v1/workers/webhooks/jira_cloud",
            json={"issue": {"key": "PROJ-1"}},
            headers={"X-Org-Id": str(uuid.uuid4())},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "submitted"
        assert capture["committed"] is True
        assert capture["kw"]["repo"] == "acme/api"
        assert capture["kw"]["trigger_source"] == "jira_cloud_webhook"
    finally:
        _teardown(app_with_router)


def test_label_miss_returns_ignored(app_with_router) -> None:
    ev = _ev(kind="labeled", labels=["bug"], external_id="PROJ-1")
    mapping = {
        "PROJ": {
            "pool_id": str(uuid.uuid4()),
            "trigger_label": "ai-worker",
        }
    }
    capture = _setup(app_with_router, ev=ev, mapping=mapping)
    try:
        client = TestClient(app_with_router)
        r = client.post(
            "/v1/workers/webhooks/jira_cloud",
            json={"issue": {"key": "PROJ-1"}},
            headers={"X-Org-Id": str(uuid.uuid4())},
        )
        assert r.status_code == 202
        assert r.json()["status"] == "ignored"
        assert "kw" not in capture
    finally:
        _teardown(app_with_router)


def test_bad_signature_ignored(app_with_router) -> None:
    # Tracker returns None when signature fails.
    capture = _setup(app_with_router, ev=None, mapping={})
    try:
        client = TestClient(app_with_router)
        r = client.post(
            "/v1/workers/webhooks/jira_cloud",
            json={"issue": {}},
            headers={"X-Org-Id": str(uuid.uuid4())},
        )
        assert r.status_code == 202
        assert r.json()["status"] == "ignored"
    finally:
        _teardown(app_with_router)
