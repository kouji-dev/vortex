"""Tests for memory_remember tool — writes worker-scoped memory."""

from __future__ import annotations

import uuid

import pytest

from ai_portal.workers.tools.providers import memory_remember as mm_mod
from ai_portal.workers.tools.providers.memory_remember import MemoryRememberTool


class _FakeStored:
    def __init__(self, mid):
        self.id = mid


class _FakeMemorySvc:
    def __init__(self):
        self.calls: list[dict] = []

    async def add_manual(self, **kw):
        self.calls.append(dict(kw))
        return _FakeStored(uuid.uuid4())


@pytest.mark.asyncio
async def test_memory_remember_writes_with_worker_scope(harness, monkeypatch) -> None:
    fake = _FakeMemorySvc()
    monkeypatch.setattr(mm_mod, "_build_memory_service", lambda _s: fake, raising=True)

    org_uuid = uuid.uuid4()
    _sb, _h, ctx, rec = await harness(
        pool_settings={
            "memory_session": object(),
            "repo_id": "repo-xyz",
            "memory_org_id": org_uuid,
            "memory_actor_user_id": 42,
        }
    )
    r = await MemoryRememberTool().invoke(
        {"text": "use pytest -x", "type": "preference"}, ctx
    )
    assert r.ok is True
    call = fake.calls[0]
    assert call["text"] == "use pytest -x"
    assert call["type"] == "preference"
    assert call["scope_kind"] == "assistant"
    assert call["scope_ids"] == ["repo-xyz"]
    assert call["org_id"] == org_uuid
    assert call["actor_user_id"] == 42
    # Tagged for worker provenance.
    assert "worker" in call["tags"]
    assert "repo:repo-xyz" in call["tags"]
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
async def test_memory_remember_no_session_errors(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await MemoryRememberTool().invoke({"text": "x"}, ctx)
    assert r.ok is False
    assert "memory_session" in (r.error or "")


@pytest.mark.asyncio
async def test_memory_remember_audits(harness, monkeypatch) -> None:
    fake = _FakeMemorySvc()
    monkeypatch.setattr(mm_mod, "_build_memory_service", lambda _s: fake, raising=True)
    org_uuid = uuid.uuid4()
    _sb, _h, ctx, rec = await harness(
        pool_settings={
            "memory_session": object(),
            "repo_id": "r",
            "memory_org_id": org_uuid,
            "memory_actor_user_id": 1,
        }
    )
    await MemoryRememberTool().invoke({"text": "abc"}, ctx)
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.memory_remember"
    assert audit["payload"]["repo_id"] == "r"
    assert "memory_id" in audit["payload"]
