"""Pure-logic tests for workers/router helpers — no DB, no HTTP."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from ai_portal.workers.router import (
    _approval_to_out,
    _artifact_to_out,
    _pool_to_out,
    _run_to_out,
    _sse_pack,
    _task_to_out,
)


def _ns(**kw):
    return SimpleNamespace(**kw)


def test_sse_pack_format() -> None:
    ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    out = _sse_pack("rec-1", "agent_thought", {"text": "hi"}, ts)
    # SSE shape: id, event, data, blank-line terminator
    lines = out.split("\n")
    assert lines[0] == "id: rec-1"
    assert lines[1] == "event: agent_thought"
    assert lines[2].startswith("data: ")
    body = json.loads(lines[2][len("data: ") :])
    assert body["id"] == "rec-1"
    assert body["kind"] == "agent_thought"
    assert body["payload"] == {"text": "hi"}
    assert body["ts"].startswith("2026-05-28")
    # trailing blank line
    assert out.endswith("\n\n")


def test_task_to_out_passes_fields() -> None:
    t = _ns(
        id="t-1",
        org_id="o-1",
        pool_id="p-1",
        title="T",
        description="D",
        repo="acme/api",
        base_branch="main",
        status="executing",
        trigger_source="rest_api",
        created_by="u-1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=None,
    )
    out = _task_to_out(t)
    assert out.id == "t-1"
    assert out.repo == "acme/api"
    assert out.status == "executing"


def test_task_to_out_handles_missing_pool() -> None:
    t = _ns(
        id="t-1",
        org_id="o-1",
        pool_id=None,
        title="T",
        description=None,
        repo=None,
        base_branch="main",
        status="queued",
        trigger_source="rest_api",
        created_by=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=None,
    )
    out = _task_to_out(t)
    assert out.pool_id is None
    assert out.description == ""


def test_run_to_out_fields() -> None:
    r = _ns(
        id="r-1",
        task_id="t-1",
        attempt_no=2,
        status="executing",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        cost_cents=42,
        error=None,
    )
    out = _run_to_out(r)
    assert out.attempt_no == 2 and out.cost_cents == 42


def test_pool_to_out_defaults_lists_and_dicts() -> None:
    p = _ns(
        id="p-1",
        org_id="o-1",
        name="default",
        template="python",
        sandbox_provider="docker",
        repo_allow_list_json=None,
        budget_cents_per_task=1000,
        default_model="m",
        settings_json=None,
        enabled=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    out = _pool_to_out(p)
    assert out.repo_allow_list == []
    assert out.settings == {}


def test_artifact_to_out() -> None:
    a = _ns(
        id="a-1",
        run_id="r-1",
        kind="pr_url",
        ref="https://github.com/x/y/pull/1",
        meta_json={"sha": "abc"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    out = _artifact_to_out(a)
    assert out.ref.endswith("/pull/1")
    assert out.meta == {"sha": "abc"}


def test_approval_to_out() -> None:
    a = _ns(
        id="a-1",
        task_id="t-1",
        kind="pr",
        requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        decided_at=None,
        decided_by=None,
        decision=None,
        reason=None,
        required_approvers=2,
    )
    out = _approval_to_out(a)
    assert out.required_approvers == 2 and out.decision is None
