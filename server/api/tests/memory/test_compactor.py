"""Phase H — compactor signatures."""
from __future__ import annotations

import inspect

from ai_portal.memory.workers import compactor


def test_compact_org_signature() -> None:
    sig = inspect.signature(compactor.compact_org)
    assert "session" in sig.parameters
    assert "org_id" in sig.parameters
    assert "threshold" in sig.parameters
    assert inspect.iscoroutinefunction(compactor.compact_org)
