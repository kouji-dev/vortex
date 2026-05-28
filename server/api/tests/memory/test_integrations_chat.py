"""Phase I — chat integration hooks."""
from __future__ import annotations

import inspect

import pytest

from ai_portal.memory.integrations import chat
from ai_portal.memory.recallers.protocol import Recalled


def test_recall_for_turn_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(chat.recall_for_turn)


def test_extract_async_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(chat.extract_async)


def test_extract_on_close_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(chat.extract_on_close)


def test_render_system_block_empty() -> None:
    assert chat.render_system_block([]) == ""


def test_render_system_block_lists_items() -> None:
    items = [
        Recalled(memory_id="m1", text="user prefers TS", score=0.9),
        Recalled(memory_id="m2", text="user works at Acme", score=0.8),
    ]
    block = chat.render_system_block(items)
    assert "Memories:" in block
    assert "user prefers TS" in block
    assert "user works at Acme" in block


def test_injected_memories_has_any() -> None:
    i = chat.InjectedMemories(items=[])
    assert not i.has_any()
    i.items.append(Recalled(memory_id="m1", text="x", score=0.1))
    assert i.has_any()
