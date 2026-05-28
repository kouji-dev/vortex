"""on_conversation_close hook + dedicated worker.

We monkeypatch ``memory.jobs`` so the test is purely about the hook's
serialisation of payload + the worker's drain loop — no DB session needed.
"""
from __future__ import annotations

import inspect
import uuid as _uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pytest

from ai_portal.memory.integrations import chat as chat_mod
from ai_portal.memory.workers import conversation_close as cc_worker


class _ScopeKindStub(str, Enum):
    conversation = "conversation"
    user = "user"


@dataclass
class _Job:
    id: _uuid.UUID
    org_id: _uuid.UUID
    scope_kind: _ScopeKindStub
    payload_json: dict[str, Any]


@pytest.fixture
def jobs_capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace _jobs.enqueue / claim_next / finish with in-memory stubs."""
    state: dict[str, Any] = {"queue": [], "finished": []}

    async def fake_enqueue(session, *, org_id, kind, scope_kind, payload):
        j = _Job(
            id=_uuid.uuid4(),
            org_id=org_id,
            scope_kind=_ScopeKindStub(scope_kind),
            payload_json={"kind": kind, **payload},
        )
        state["queue"].append(j)
        return j

    async def fake_claim_next(session, *, kind: str | None = None):
        for j in list(state["queue"]):
            if kind is None or j.payload_json.get("kind") == kind:
                state["queue"].remove(j)
                return j
        return None

    async def fake_finish(session, job_id, *, status="done", error=None):
        state["finished"].append((job_id, status, error))

    from ai_portal.memory import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "enqueue", fake_enqueue)
    monkeypatch.setattr(jobs_mod, "claim_next", fake_claim_next)
    monkeypatch.setattr(jobs_mod, "finish", fake_finish)
    monkeypatch.setattr(cc_worker._jobs, "claim_next", fake_claim_next)
    monkeypatch.setattr(cc_worker._jobs, "finish", fake_finish)
    return state


def test_on_conversation_close_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(chat_mod.on_conversation_close)


@pytest.mark.asyncio
async def test_on_conversation_close_enqueues_batch_job(jobs_capture) -> None:
    org_id = _uuid.uuid4()
    transcript = [
        {"role": "user", "content": "hi", "turn_id": "t1", "ts": 1.0},
        {"role": "assistant", "content": "hello", "turn_id": "t2", "ts": 2.0},
    ]
    await chat_mod.on_conversation_close(
        session=None,
        org_id=org_id,
        actor_user_id="42",
        conversation_id=7,
        transcript=transcript,
    )
    assert len(jobs_capture["queue"]) == 1
    job = jobs_capture["queue"][0]
    payload = job.payload_json
    assert payload["kind"] == "conversation_close"
    assert payload["trigger"] == "conversation_close"
    assert payload["conversation_id"] == 7
    assert payload["actor_user_id"] == "42"
    assert payload["batched"] is True
    assert len(payload["turns"]) == 2
    assert job.org_id == org_id


@pytest.mark.asyncio
async def test_on_conversation_close_accepts_string_org_id(jobs_capture) -> None:
    org_uuid = _uuid.uuid4()
    await chat_mod.on_conversation_close(
        session=None,
        org_id=str(org_uuid),
        actor_user_id="u1",
        conversation_id="conv-1",
        transcript=[],
    )
    assert jobs_capture["queue"][0].org_id == org_uuid


@pytest.mark.asyncio
async def test_worker_drains_queued_job(monkeypatch: pytest.MonkeyPatch, jobs_capture) -> None:
    # Pre-enqueue a close job via the public hook
    await chat_mod.on_conversation_close(
        session=None,
        org_id=_uuid.uuid4(),
        actor_user_id="u9",
        conversation_id=99,
        transcript=[{"role": "user", "content": "hi", "turn_id": "t1", "ts": 1.0}],
    )

    # Stub MemoryService.extract so we don't touch real extractors / DB
    calls: list[tuple] = []

    class _SvcStub:
        def __init__(self, session) -> None:
            pass

        async def extract(self, turns, scope, opts):
            calls.append((turns, scope, opts))

    monkeypatch.setattr(cc_worker, "MemoryService", _SvcStub)

    n = await cc_worker.run_once(session=None, max_jobs=5)
    assert n == 1
    assert len(calls) == 1
    turns, scope, opts = calls[0]
    assert len(turns) == 1
    assert turns[0].turn_id == "t1"
    assert scope.scope_kind == "conversation"
    assert scope.conversation_id == 99
    assert opts.model == "claude-sonnet-4-6"
    # Finished as done
    assert jobs_capture["finished"][-1][1] == "done"


@pytest.mark.asyncio
async def test_worker_drains_zero_jobs_when_empty(monkeypatch: pytest.MonkeyPatch, jobs_capture) -> None:
    monkeypatch.setattr(cc_worker, "MemoryService", lambda s: None)
    n = await cc_worker.run_once(session=None, max_jobs=10)
    assert n == 0


@pytest.mark.asyncio
async def test_worker_marks_job_error_on_extract_failure(
    monkeypatch: pytest.MonkeyPatch, jobs_capture
) -> None:
    await chat_mod.on_conversation_close(
        session=None,
        org_id=_uuid.uuid4(),
        actor_user_id="u1",
        conversation_id=1,
        transcript=[],
    )

    class _SvcExploder:
        def __init__(self, session) -> None:
            pass

        async def extract(self, turns, scope, opts):
            raise RuntimeError("boom")

    monkeypatch.setattr(cc_worker, "MemoryService", _SvcExploder)

    n = await cc_worker.run_once(session=None, max_jobs=5)
    assert n == 1
    assert jobs_capture["finished"][-1][1] == "error"
    assert "boom" in (jobs_capture["finished"][-1][2] or "")
