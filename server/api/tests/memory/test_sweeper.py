"""Phase H — sweeper signatures (DB integration covered elsewhere)."""
from __future__ import annotations

import inspect

from ai_portal.memory.workers import sweeper


def test_sweep_expired_signature() -> None:
    sig = inspect.signature(sweeper.sweep_expired)
    assert "session" in sig.parameters
    assert "now" in sig.parameters
    assert inspect.iscoroutinefunction(sweeper.sweep_expired)


def test_purge_old_deleted_signature() -> None:
    sig = inspect.signature(sweeper.purge_old_deleted)
    assert "retention_days" in sig.parameters
    assert inspect.iscoroutinefunction(sweeper.purge_old_deleted)


def test_run_once_signature() -> None:
    assert inspect.iscoroutinefunction(sweeper.run_once)
