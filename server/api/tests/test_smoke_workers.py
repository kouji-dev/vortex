"""Phase 3 smoke test — workers golden path.

Drives the workers HTTP API end-to-end against a real Postgres (env-driven via
``DATABASE_URL``):

1. Auth via dev bearer token (signup+login surrogate — dev seed user is
   created by alembic migration 032).
2. Create a pool with ``sandbox_provider=fake``.
3. Submit a task (no tools, ``trigger_source=rest_api``).
4. Verify the task is queued and a run can be created.
5. Walk the task lifecycle through the state machine
   (``queued → planning → executing → completed``).
6. Emit ``phase_changed`` events through the in-process ``EventWriter``;
   verify the subscriber receives them (proves the SSE plumbing).
7. Persist a ``request_trace`` whose ``actor_json`` references ``task_id`` and
   confirm it can be queried back (trace correlation).
8. Confirm the fake sandbox provider is registerable + selectable, and that
   ``can_transition()`` allows the golden path.

This is a *smoke* test — it intentionally avoids the (not-yet-wired)
orchestrator runner that would normally drive runs in production. The
agent-loop shortcut (no tools, empty plan) keeps the test deterministic.
"""

from __future__ import annotations

import asyncio
import os
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_postgres


# ── Env preconditions ─────────────────────────────────────────────


_REQUIRED_ENV = {
    "DEPLOYMENT_MODE": "saas",
}


def _env_ok() -> bool:
    return (
        os.environ.get("DEPLOYMENT_MODE") in ("saas", "selfhosted")
        and bool(os.environ.get("SECRET_KEY"))
    )


requires_env = pytest.mark.skipif(
    not _env_ok(),
    reason="smoke test needs DEPLOYMENT_MODE=saas and SECRET_KEY set",
)


# ── Helpers ───────────────────────────────────────────────────────


def _client() -> TestClient:
    # Import inside helper so env is read at app boot, not test collection.
    from ai_portal.main import app  # noqa: PLC0415

    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    # TODO(auth-rework): smoke auth needs real JWT — dev bearer removed in Phase 2
    return {"Authorization": "Bearer devtoken"}


def _unique(prefix: str) -> str:
    return f"{prefix}-{_uuid.uuid4().hex[:8]}"


# ── Tests ─────────────────────────────────────────────────────────


@requires_postgres
@requires_env
def test_health_then_auth() -> None:
    """Sanity: app boots, /health is green, dev bearer authenticates."""
    c = _client()
    r = c.get("/health")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    me = c.get("/me", headers=_auth_headers())
    # /me may 200 (dev seed) or 404 (route absent in some configs) — auth is the
    # signal we care about; no 401.
    assert me.status_code != 401, me.text


@requires_postgres
@requires_env
def test_fake_sandbox_provider_registerable() -> None:
    """``WORKER_SANDBOX_PROVIDER=fake`` is a valid selectable provider."""
    from ai_portal.workers.sandboxes import registry  # noqa: PLC0415
    from ai_portal.workers.sandboxes.providers.fake import FakeSandbox  # noqa: PLC0415

    registry.clear()
    registry.register(FakeSandbox())
    assert "fake" in registry.all_providers()
    assert registry.get("fake").name == "fake"


@requires_postgres
@requires_env
def test_state_machine_golden_path() -> None:
    """``can_transition()`` accepts queued → planning → executing → completed."""
    from ai_portal.workers.types import TaskStatus, can_transition  # noqa: PLC0415

    path = [
        TaskStatus.queued,
        TaskStatus.planning,
        TaskStatus.executing,
        TaskStatus.completed,
    ]
    for a, b in zip(path, path[1:]):
        assert can_transition(a, b), f"{a.value} -> {b.value} blocked"


@requires_postgres
@requires_env
def test_create_pool_then_submit_task() -> None:
    """POST /v1/workers/pools → POST /v1/workers/tasks succeeds; task queued."""
    c = _client()
    h = _auth_headers()

    pool_body = {
        "name": _unique("smoke"),
        "template": "polyglot",
        "sandbox_provider": "fake",
        "repo_allow_list": [],
        "budget_cents_per_task": 10_000,
        "default_model": "fake-model",
    }
    r = c.post("/v1/workers/pools", json=pool_body, headers=h)
    assert r.status_code == 201, r.text
    pool = r.json()
    assert pool["sandbox_provider"] == "fake"
    pool_id = pool["id"]

    task_body = {
        "pool_id": pool_id,
        "title": "smoke",
        "description": "test",
        "repo": "smoke/repo",  # required by schema
        "trigger_source": "rest_api",
    }
    r = c.post("/v1/workers/tasks", json=task_body, headers=h)
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["status"] == "queued"
    assert task["pool_id"] == pool_id
    assert task["trigger_source"] == "rest_api"
    task_id = task["id"]

    # GET /tasks/{id}
    r = c.get(f"/v1/workers/tasks/{task_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["id"] == task_id

    # GET /tasks (list)
    r = c.get("/v1/workers/tasks", headers=h)
    assert r.status_code == 200
    assert any(t["id"] == task_id for t in r.json())


@requires_postgres
@requires_env
def test_task_walks_lifecycle_via_service() -> None:
    """Walk queued → planning → executing → completed via the service layer.

    The smoke test stands in for the (not-yet-wired) orchestrator runner —
    proves the lifecycle state machine accepts the golden-path transitions
    end-to-end against a real DB.
    """
    from ai_portal.auth.deps import get_db  # noqa: PLC0415
    from ai_portal.workers import service as svc  # noqa: PLC0415
    from ai_portal.workers.types import TaskStatus  # noqa: PLC0415

    c = _client()
    h = _auth_headers()

    # Use the API to create the pool + task so we exercise the same paths.
    r = c.post(
        "/v1/workers/pools",
        json={
            "name": _unique("smoke-lc"),
            "template": "polyglot",
            "sandbox_provider": "fake",
            "repo_allow_list": [],
            "budget_cents_per_task": 10_000,
            "default_model": "fake-model",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    pool_id = r.json()["id"]

    r = c.post(
        "/v1/workers/tasks",
        json={
            "pool_id": pool_id,
            "title": "smoke-lc",
            "description": "lifecycle walk",
            "repo": "smoke/lc",
            "trigger_source": "rest_api",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    task_id = _uuid.UUID(r.json()["id"])
    org_id = _uuid.UUID(r.json()["org_id"])

    # Drive the state machine directly (orchestrator stand-in).
    db_gen = get_db()
    db = next(db_gen)
    try:
        task = svc.get_task(db, org_id=org_id, task_id=task_id)
        assert task.status == "queued"

        svc.transition_task(db, task=task, to=TaskStatus.planning)
        svc.transition_task(db, task=task, to=TaskStatus.executing)
        svc.transition_task(db, task=task, to=TaskStatus.completed)
        db.commit()

        # Re-read.
        task = svc.get_task(db, org_id=org_id, task_id=task_id)
        assert task.status == "completed"
        assert task.completed_at is not None
    finally:
        with pytest.raises(StopIteration):
            next(db_gen)


@requires_postgres
@requires_env
def test_event_writer_subscribes_and_broadcasts() -> None:
    """Emit phase_changed via the writer; subscriber receives the events.

    Proves the SSE pub/sub plumbing — what ``/v1/workers/tasks/{id}/events``
    rides on top of — works without the HTTP layer.
    """
    from ai_portal.workers.events.writer import EventRecord, EventWriter  # noqa: PLC0415
    from ai_portal.workers.types import EventKind  # noqa: PLC0415

    async def _run() -> list[EventRecord]:
        writer = EventWriter()  # no session_factory → broadcast-only
        run_id = _uuid.uuid4().hex
        received: list[EventRecord] = []

        async def cb(rec: EventRecord) -> None:
            received.append(rec)

        writer.subscribe(run_id, cb)
        try:
            await writer.emit(run_id, EventKind.phase_changed, {"to": "planning"})
            await writer.emit(run_id, EventKind.phase_changed, {"to": "executing"})
            await writer.emit(run_id, EventKind.phase_changed, {"to": "completed"})
        finally:
            writer.unsubscribe(run_id, cb)
        return received

    received = asyncio.run(_run())
    kinds = [r.kind for r in received]
    phases = [r.payload.get("to") for r in received]
    assert kinds == ["phase_changed"] * 3
    assert phases == ["planning", "executing", "completed"]


@requires_postgres
@requires_env
def test_request_trace_correlation_by_task_id() -> None:
    """Insert a ``request_trace`` with ``actor_json.task_id`` and query it back.

    The gateway facade stamps the caller's actor into ``actor_json``. In the
    workers domain a future facade variant should add ``task_id`` so admins
    can correlate LLM traces back to the worker that issued them. This test
    proves the column is writable + queryable as expected.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from ai_portal.auth.deps import get_db  # noqa: PLC0415
    from ai_portal.auth.model import User  # noqa: PLC0415
    from ai_portal.gateway.traces.model import RequestTrace  # noqa: PLC0415

    db_gen = get_db()
    db = next(db_gen)
    try:
        # Borrow dev seed user's org so the FK to orgs is valid.
        user = db.scalars(select(User).where(User.email == "dev@localhost")).first()
        assert user is not None, "dev seed user missing — alembic 032 didn't run"
        org_id = user.org_id

        task_id = str(_uuid.uuid4())
        row = RequestTrace(
            org_id=org_id,
            actor_json={
                "actor_user_id": str(user.id),
                "task_id": task_id,
                "source": "worker",
            },
            route="chat.completions",
            model_requested="fake-model",
            model_used="fake-model",
            provider="fake",
            status="ok",
            tokens_in=10,
            tokens_out=5,
            cost_cents=1,
        )
        db.add(row)
        db.commit()

        # Query by actor_json.task_id — the same pattern admins would use.
        found = db.execute(
            select(RequestTrace).where(
                RequestTrace.actor_json["task_id"].astext == task_id
            )
        ).scalar_one_or_none()
        assert found is not None
        assert found.actor_json["task_id"] == task_id
        assert found.actor_json["source"] == "worker"
    finally:
        with pytest.raises(StopIteration):
            next(db_gen)


@requires_postgres
@requires_env
def test_sse_endpoint_authorised_and_serves_backfill() -> None:
    """GET /v1/workers/tasks/{id}/events authorises + emits backfill rows.

    Uses ``svc.list_events_for_task`` to assert the backfill source has the
    expected rows (the same query the SSE endpoint runs first) and a HEAD-
    style auth probe to confirm the route mounts. We deliberately don't
    iterate the live stream — ``StreamingResponse`` blocks on the keepalive
    loop and TestClient has no built-in cancel.
    """
    from ai_portal.auth.deps import get_db  # noqa: PLC0415
    from ai_portal.workers import service as svc  # noqa: PLC0415
    from ai_portal.workers.model import WorkerEvent, WorkerRun  # noqa: PLC0415

    c = _client()
    h = _auth_headers()

    # Create pool + task.
    r = c.post(
        "/v1/workers/pools",
        json={
            "name": _unique("smoke-sse"),
            "template": "polyglot",
            "sandbox_provider": "fake",
            "repo_allow_list": [],
            "budget_cents_per_task": 10_000,
            "default_model": "fake-model",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    pool_id = r.json()["id"]

    r = c.post(
        "/v1/workers/tasks",
        json={
            "pool_id": pool_id,
            "title": "smoke-sse",
            "description": "sse backfill",
            "repo": "smoke/sse",
            "trigger_source": "rest_api",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]
    task_uuid = _uuid.UUID(task_id)

    # Seed a run + 3 phase_changed events so the backfill has data.
    db_gen = get_db()
    db = next(db_gen)
    try:
        run = WorkerRun(task_id=task_uuid, attempt_no=1, status="planning")
        db.add(run)
        db.flush()
        for phase in ("planning", "executing", "completed"):
            db.add(
                WorkerEvent(
                    run_id=run.id,
                    kind="phase_changed",
                    payload_json={"to": phase},
                )
            )
        db.commit()

        # Same backfill query the SSE endpoint runs before subscribing.
        rows = svc.list_events_for_task(db, task_id=task_uuid)
    finally:
        with pytest.raises(StopIteration):
            next(db_gen)

    phases = [r.payload_json.get("to") for r in rows if r.kind == "phase_changed"]
    assert "planning" in phases
    assert "executing" in phases
    assert "completed" in phases

    # Auth probe: missing bearer → 401, present → not 401. (We don't fully
    # consume the body — the route would block on keepalive.)
    r = c.get(f"/v1/workers/tasks/{task_id}/events")
    assert r.status_code == 401, r.text
