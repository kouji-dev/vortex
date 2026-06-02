"""Pure-logic tests for the worker-instance service + router converters.

No real DB: validation in ``spawn_worker`` runs before any persistence, so a
tiny fake session (no-op add/flush) exercises the validation + happy path.
``build_runtime_config`` and the router converters are pure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_portal.workers import instances_service as svc
from ai_portal.workers.instances_router import (
    _change_to_out,
    _msg_to_out,
    _run_to_out,
    _worker_to_out,
)


class _FakeSession:
    """Minimal Session double: records added rows, no-op flush."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)

    def flush(self) -> None:
        pass


_ORG = "11111111-1111-1111-1111-111111111111"


# ── spawn_worker validation ──────────────────────────────────────


def test_spawn_rejects_bad_mode() -> None:
    with pytest.raises(svc.InvalidArg):
        svc.spawn_worker(
            _FakeSession(), org_id=_ORG, name="w", model="m", mode="bogus"
        )


def test_spawn_rejects_bad_runtime() -> None:
    with pytest.raises(svc.InvalidArg):
        svc.spawn_worker(
            _FakeSession(), org_id=_ORG, name="w", model="m", runtime="gemini"
        )


def test_spawn_rejects_unknown_skill() -> None:
    with pytest.raises(svc.InvalidArg):
        svc.spawn_worker(
            _FakeSession(), org_id=_ORG, name="w", model="claude-sonnet-4-6", skills=["ghost"]
        )


def test_spawn_happy_path_provisions_worker_row() -> None:
    db = _FakeSession()
    w = svc.spawn_worker(
        db,
        org_id=_ORG,
        name="ship-fix",
        model="claude-sonnet-4-6",
        mode="interactive",
        runtime="claude",
        connector={"kind": "gitlab", "project": "acme/api"},
        repo_url="https://gitlab.com/acme/api.git",
        skills=["fix-bug"],
        created_by="42",
    )
    assert w in db.added
    assert w.state == "provisioning"
    assert w.mode == "interactive"
    assert w.runtime == "claude"
    # skills folded into connector_json for the runner to materialize
    assert w.connector_json["skills"] == ["fix-bug"]
    assert w.connector_json["kind"] == "gitlab"


# ── runtime config wiring (gateway base_url) ─────────────────────


def test_build_runtime_config_routes_through_gateway() -> None:
    w = SimpleNamespace(
        model="claude-sonnet-4-6", connector_json={"skills": ["fix-bug"]}
    )
    cfg = svc.build_runtime_config(w, gateway_base_url="http://gw/v1")
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.gateway_base_url == "http://gw/v1"
    assert cfg.skills == ["fix-bug"]


def test_build_runtime_config_handles_no_skills() -> None:
    w = SimpleNamespace(model="m", connector_json={})
    cfg = svc.build_runtime_config(w, gateway_base_url="http://gw/v1")
    assert cfg.skills == []


# ── router converters ────────────────────────────────────────────


def _ts() -> datetime:
    return datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_worker_to_out_maps_fields() -> None:
    import uuid

    wid = uuid.uuid4()
    w = SimpleNamespace(
        id=wid,
        org_id=uuid.UUID(_ORG),
        pool_id=None,
        name="w",
        state="idle",
        mode="autonomous",
        model="m",
        runtime="codex",
        connector_json={"kind": "gitlab"},
        repo_url="r",
        sandbox_id=None,
        trigger_source="github_issue_comment",
        created_by="42",
        created_at=_ts(),
        last_active_at=None,
    )
    out = _worker_to_out(w)
    assert out.id == str(wid)
    assert out.state == "idle"
    assert out.mode == "autonomous"
    assert out.runtime == "codex"
    assert out.connector == {"kind": "gitlab"}
    assert out.pool_id is None


def test_run_to_out_maps_fields() -> None:
    import uuid

    rid, wid = uuid.uuid4(), uuid.uuid4()
    r = SimpleNamespace(
        id=rid,
        worker_id=wid,
        seq_no=3,
        user_message="do it",
        status="running",
        started_at=_ts(),
        ended_at=None,
        cost_cents=0,
        error=None,
    )
    out = _run_to_out(r)
    assert out.seq_no == 3
    assert out.status == "running"
    assert out.worker_id == str(wid)


def test_change_and_msg_converters() -> None:
    import uuid

    cid, rid = uuid.uuid4(), uuid.uuid4()
    c = SimpleNamespace(
        id=cid,
        run_id=rid,
        file_path="src/app.py",
        change_kind="modified",
        additions=4,
        deletions=1,
        diff_ref="@@ -1 +1 @@",
    )
    co = _change_to_out(c)
    assert co.file_path == "src/app.py"
    assert co.additions == 4

    mid, wid = uuid.uuid4(), uuid.uuid4()
    m = SimpleNamespace(
        id=mid, worker_id=wid, run_id=rid, role="user", content="hi", ts=_ts()
    )
    mo = _msg_to_out(m)
    assert mo.role == "user"
    assert mo.run_id == str(rid)
