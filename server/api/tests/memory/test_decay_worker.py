"""Phase H — importance decay worker signatures."""
from __future__ import annotations

import inspect

from ai_portal.memory.workers import decay


def test_run_decay_signature() -> None:
    sig = inspect.signature(decay.run_decay)
    assert "session" in sig.parameters
    assert "now" in sig.parameters
    assert inspect.iscoroutinefunction(decay.run_decay)
