import pytest
from pydantic import ValidationError

from ai_portal.catalog.providers.events import (
    ProviderStreamEvent, TextDeltaEvent, ThinkingDeltaEvent,
    ToolCallRequestEvent, UsageEvent, ServerToolUseEvent,
    ProviderErrorEvent, IterationCompleteEvent, CitationEvent,
)


def test_text_delta():
    ev = ProviderStreamEvent.model_validate({"type": "text_delta", "text": "hi"})
    assert isinstance(ev.root, TextDeltaEvent)


def test_usage_event_shape():
    ev = ProviderStreamEvent.model_validate({
        "type": "usage",
        "input_tokens": 10, "output_tokens": 20,
        "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0,
    })
    assert ev.root.output_tokens == 20


def test_tool_call_request():
    ev = ProviderStreamEvent.model_validate({
        "type": "tool_call_request",
        "call_id": "call_1", "tool_name": "web_search", "arguments": {"q": "x"},
    })
    assert isinstance(ev.root, ToolCallRequestEvent)


def test_unknown_discriminator_rejected():
    with pytest.raises(ValidationError):
        ProviderStreamEvent.model_validate({"type": "wat"})


def test_thinking_delta_event():
    ev = ProviderStreamEvent.model_validate({"type": "thinking_delta", "text": "hmm"})
    assert isinstance(ev.root, ThinkingDeltaEvent)
    assert ev.root.text == "hmm"


def test_server_tool_use_event():
    ev = ProviderStreamEvent.model_validate({"type": "server_tool_use", "tool_name": "web_search", "input": {"q": "x"}})
    assert isinstance(ev.root, ServerToolUseEvent)
    assert ev.root.tool_name == "web_search"


def test_citation_event():
    ev = ProviderStreamEvent.model_validate({"type": "citation", "url": "https://example.com"})
    assert isinstance(ev.root, CitationEvent)
    assert ev.root.url == "https://example.com"


def test_iteration_complete_event():
    ev = ProviderStreamEvent.model_validate({"type": "iteration_complete", "stop_reason": "end_turn"})
    assert isinstance(ev.root, IterationCompleteEvent)
    assert ev.root.stop_reason == "end_turn"


def test_provider_error_event():
    ev = ProviderStreamEvent.model_validate({"type": "provider_error", "code": "E1", "message": "fail"})
    assert isinstance(ev.root, ProviderErrorEvent)
    assert ev.root.code == "E1"


def test_iteration_complete_rejects_invalid_stop_reason():
    with pytest.raises(ValidationError):
        ProviderStreamEvent.model_validate({"type": "iteration_complete", "stop_reason": "banana"})
