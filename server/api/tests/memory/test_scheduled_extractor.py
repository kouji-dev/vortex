"""Phase H — scheduled extractor signature."""
from __future__ import annotations

import inspect

from ai_portal.memory.workers import scheduled_extractor


def test_run_once_signature() -> None:
    sig = inspect.signature(scheduled_extractor.run_once)
    assert "session" in sig.parameters
    assert "max_jobs" in sig.parameters
    assert inspect.iscoroutinefunction(scheduled_extractor.run_once)
