from unittest.mock import MagicMock

from ai_portal.api.conversations import _build_memory_block


def test_memory_block_with_active_memories():
    memories = [
        MagicMock(content="Prefers Python", is_active=True),
        MagicMock(content="Works at Acme", is_active=True),
    ]
    block = _build_memory_block(memories)
    assert "Prefers Python" in block
    assert "What you know about this user" in block


def test_memory_block_empty_when_no_active():
    assert _build_memory_block([]) == ""
