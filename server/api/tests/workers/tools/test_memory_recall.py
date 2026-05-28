"""Tests for the memory_recall tool — calls MemoryService.recall."""

from __future__ import annotations

import pytest

from ai_portal.workers.tools.providers import memory_recall as mr_mod
from ai_portal.workers.tools.providers.memory_recall import MemoryRecallTool


class _FakeRecalled:
    def __init__(self, mid, text, score):
        self.memory_id = mid
        self.text = text
        self.score = score
        self.explain = {}


class _FakeMemorySvc:
    def __init__(self, results):
        self._results = results
        self.calls: list[dict] = []

    async def recall(self, query, scope, opts=None):
        self.calls.append(
            {
                "query": query,
                "org_id": scope.org_id,
                "actor_user_id": scope.actor_user_id,
                "assistant_id": getattr(scope, "assistant_id", None),
                "top_k": getattr(opts, "top_k", None),
            }
        )
        return list(self._results)


@pytest.mark.asyncio
async def test_memory_recall_calls_service_with_worker_filter(
    harness, monkeypatch
) -> None:
    fake = _FakeMemorySvc(
        [_FakeRecalled("m1", "user prefers tabs", 0.93)]
    )
    monkeypatch.setattr(mr_mod, "_build_memory_service", lambda _s: fake, raising=True)

    _sb, _h, ctx, rec = await harness(
        pool_settings={"memory_session": object(), "repo_id": "repo-abc"}
    )
    r = await MemoryRecallTool().invoke({"query": "indent style"}, ctx)
    assert r.ok is True
    assert r.output["results"][0]["text"] == "user prefers tabs"
    assert fake.calls[0]["query"] == "indent style"
    # Worker scope is set via assistant_id = repo_id.
    assert fake.calls[0]["assistant_id"] == "repo-abc"
    assert fake.calls[0]["org_id"] == "org-1"
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
async def test_memory_recall_no_session_errors(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await MemoryRecallTool().invoke({"query": "x"}, ctx)
    assert r.ok is False
    assert "memory_session" in (r.error or "")


@pytest.mark.asyncio
async def test_memory_recall_audits_query(harness, monkeypatch) -> None:
    fake = _FakeMemorySvc([_FakeRecalled("m1", "t", 0.9)])
    monkeypatch.setattr(mr_mod, "_build_memory_service", lambda _s: fake, raising=True)
    _sb, _h, ctx, rec = await harness(
        pool_settings={"memory_session": object(), "repo_id": "r"}
    )
    await MemoryRecallTool().invoke({"query": "Q"}, ctx)
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.memory_recall"
    assert audit["payload"]["query"] == "Q"
    assert audit["payload"]["result_count"] == 1


@pytest.mark.asyncio
async def test_memory_recall_passes_top_k(harness, monkeypatch) -> None:
    fake = _FakeMemorySvc([])
    monkeypatch.setattr(mr_mod, "_build_memory_service", lambda _s: fake, raising=True)
    _sb, _h, ctx, _rec = await harness(
        pool_settings={"memory_session": object(), "repo_id": "r"}
    )
    await MemoryRecallTool().invoke({"query": "x", "top_k": 3}, ctx)
    assert fake.calls[0]["top_k"] == 3
