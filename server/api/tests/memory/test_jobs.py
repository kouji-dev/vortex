"""Phase H — jobs queue helper signature tests (DB-free)."""
from __future__ import annotations

import inspect

from ai_portal.memory import jobs as _jobs


def test_enqueue_signature() -> None:
    sig = inspect.signature(_jobs.enqueue)
    assert {"session", "org_id", "kind", "scope_kind", "payload"} <= set(sig.parameters)
    assert inspect.iscoroutinefunction(_jobs.enqueue)


def test_claim_next_signature() -> None:
    sig = inspect.signature(_jobs.claim_next)
    assert "session" in sig.parameters
    assert "kind" in sig.parameters
    assert inspect.iscoroutinefunction(_jobs.claim_next)


def test_finish_signature() -> None:
    sig = inspect.signature(_jobs.finish)
    assert {"session", "job_id", "status", "error"} <= set(sig.parameters)
    assert inspect.iscoroutinefunction(_jobs.finish)


def test_watermark_signature() -> None:
    sig = inspect.signature(_jobs.watermark)
    assert "session" in sig.parameters
    assert "conversation_id" in sig.parameters
    assert inspect.iscoroutinefunction(_jobs.watermark)
