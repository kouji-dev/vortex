"""Phase A2 — repository import + signature sanity.

Full DB-backed coverage lives in Phase G/J integration tests. This module
only checks that the repository constructs valid SQL clauses and exposes
the expected methods.
"""
from __future__ import annotations

import inspect

from ai_portal.memory.repository import MemoryRepo


def test_repo_has_expected_methods() -> None:
    for name in (
        "add",
        "get",
        "soft_delete",
        "restore",
        "patch",
        "list_for_actor",
        "vector_search",
        "record_use",
        "list_uses",
        "bulk_soft_delete",
        "hard_delete",
        "write_scopes",
    ):
        assert hasattr(MemoryRepo, name), name
        assert inspect.iscoroutinefunction(getattr(MemoryRepo, name)), name


def test_repo_init_takes_session() -> None:
    sig = inspect.signature(MemoryRepo.__init__)
    assert "session" in sig.parameters
