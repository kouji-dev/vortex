"""Tests for model-aware tool definition injection."""


def test_registry_returns_native_anthropic_search_for_claude_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="claude-sonnet-4-6")
    tool_types = [t.get("type") for t in tools]
    assert "web_search_20260209" in tool_types
    # Our custom web_search should NOT be present for Anthropic models
    function_names = [
        t.get("function", {}).get("name")
        for t in tools
        if t.get("type") == "function"
    ]
    assert "web_search" not in function_names


def test_registry_returns_custom_search_for_non_anthropic_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="gpt-4o")
    function_names = [
        t.get("function", {}).get("name")
        for t in tools
        if t.get("type") == "function"
    ]
    assert "web_search" in function_names
    # No native Anthropic tool for OpenAI models
    tool_types = [t.get("type") for t in tools]
    assert "web_search_20260209" not in tool_types


def test_registry_returns_gemini_search_for_gemini_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="gemini-2.5-flash")
    # Gemini uses google_search_retrieval (a dict with that key, not type="function")
    has_google_search = any("google_search_retrieval" in t for t in tools)
    assert has_google_search


def test_registry_falls_back_to_custom_search_when_no_model():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id=None)
    function_names = [
        t.get("function", {}).get("name")
        for t in tools
        if t.get("type") == "function"
    ]
    assert "web_search" in function_names


def test_registry_native_anthropic_search_has_user_location():
    from ai_portal.tools.registry import get_tool_definitions

    tools = get_tool_definitions(kb_ids=[], model_id="claude-opus-4-6")
    native = next(t for t in tools if t.get("type") == "web_search_20260209")
    assert "user_location" in native
    assert native["user_location"]["country"] == "FR"  # default
