# tests/chat/streaming/test_system_prompt.py
from ai_portal.chat.streaming.system_prompt import compose


def test_base_only():
    result = compose(base_prompt="You are helpful.", assistant_prompt=None, memory_block=None, kb_block=None, capabilities=[])
    assert result == "You are helpful."


def test_with_assistant_prompt():
    result = compose(base_prompt="Base.", assistant_prompt="Custom instructions.", memory_block=None, kb_block=None, capabilities=[])
    assert "Base." in result
    assert "Custom instructions." in result


def test_with_memory_block():
    result = compose(base_prompt="Base.", assistant_prompt=None, memory_block="User likes Python.", kb_block=None, capabilities=[])
    assert "## Memory" in result
    assert "User likes Python." in result


def test_with_kb_block():
    result = compose(base_prompt="Base.", assistant_prompt=None, memory_block=None, kb_block="KB content.", capabilities=[])
    assert "## Knowledge base" in result
    assert "KB content." in result


def test_with_capabilities():
    result = compose(base_prompt="Base.", assistant_prompt=None, memory_block=None, kb_block=None, capabilities=["web_search", "kb_search"])
    assert "## Available tools" in result
    assert "web_search" in result
    assert "kb_search" in result


def test_empty_strings_are_excluded():
    result = compose(base_prompt="Base.", assistant_prompt="", memory_block="  ", kb_block=None, capabilities=[])
    assert result == "Base."
