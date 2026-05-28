"""Phase I — assistant-scope integration."""
from __future__ import annotations

import inspect

from ai_portal.memory.integrations import assistants
from ai_portal.memory.recallers.protocol import Recalled


def test_recall_for_assistant_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(assistants.recall_for_assistant)


def test_render_assistant_block() -> None:
    out = assistants.render_assistant_block(
        [Recalled(memory_id="m", text="prefers verbose logs", score=0.7)]
    )
    assert "Assistant memory" in out
    assert "verbose logs" in out


def test_render_assistant_block_empty() -> None:
    assert assistants.render_assistant_block([]) == ""
