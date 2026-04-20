from unittest.mock import MagicMock

from ai_portal.chat.memory_context import build_memory_block as _build_memory_block


def _mem(content: str, *, is_system: bool = False, active: bool = True) -> MagicMock:
    m = MagicMock()
    m.content = content
    m.is_system = is_system
    m.is_active = active
    return m


def test_memory_block_includes_system_and_manual():
    system = _mem("Likes concise answers", is_system=True)
    manuals = [_mem("Prefers dark mode")]
    block = _build_memory_block(system_profile=system, manual_memories=manuals)
    assert "User profile:" in block
    assert "Likes concise" in block
    assert "Prefers dark mode" in block


def test_memory_block_manual_only():
    block = _build_memory_block(
        system_profile=None,
        manual_memories=[_mem("Manual fact")],
    )
    assert "Saved memories:" in block
    assert "Manual fact" in block


def test_memory_block_empty():
    assert _build_memory_block(system_profile=None, manual_memories=[]) == ""
