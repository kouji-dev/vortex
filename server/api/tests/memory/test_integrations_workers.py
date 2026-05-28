"""Phase I — worker-scope helper."""
from __future__ import annotations

import inspect

from ai_portal.memory.integrations import workers


def test_repo_scope_ids() -> None:
    assert workers.repo_scope_ids("u-1", "r-1") == ["u-1", "repo:r-1"]


def test_recall_for_repo_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(workers.recall_for_repo)
