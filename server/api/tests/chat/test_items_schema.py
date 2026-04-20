import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_portal.chat.items import (
    AssistantTextItem, CitationItem, ErrorItem, LlmCallItem,
    MemoryPillItem, ServerToolUseItem, ThinkingItem, ThreadItemModel,
    ToolCallItem, TurnEndItem, UserMessageItem,
)


def _base_kwargs(**overrides):
    return {
        "id": 1, "thread_id": 1, "turn_id": uuid.uuid4(),
        "status": "done", "created_at": datetime.now(timezone.utc),
        **overrides,
    }


def test_user_message_discriminator():
    item = UserMessageItem(**_base_kwargs(kind="user_message", data={"text": "hi", "attachments": []}))
    assert item.kind == "user_message"


def test_llm_call_requires_model_and_tokens():
    with pytest.raises(ValidationError):
        LlmCallItem(**_base_kwargs(kind="llm_call", data={}))
    item = LlmCallItem(**_base_kwargs(
        kind="llm_call", model="gpt-4",
        data={"input_tokens": 10, "output_tokens": 20, "cached_input_tokens": 0,
              "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "iteration_index": 0},
    ))
    assert item.data.input_tokens == 10


def test_threaditem_parses_from_discriminator():
    payload = _base_kwargs(
        kind="tool_call", role="assistant",
        data={"tool_name": "web_search", "params": {"q": "x"}},
    )
    item = ThreadItemModel.model_validate(payload)
    assert isinstance(item.root, ToolCallItem)


def test_turn_end_payload():
    item = TurnEndItem(**_base_kwargs(kind="turn_end", data={"reason": "done"}))
    assert item.data.reason == "done"


def test_error_kind_payload():
    item = ErrorItem(**_base_kwargs(kind="error", data={"code": "E1", "message": "boom"}))
    assert item.data.code == "E1"


def test_assistant_text_round_trip():
    item = ThreadItemModel.model_validate(_base_kwargs(kind="assistant_text", data={"text": "hello"}))
    assert isinstance(item.root, AssistantTextItem)
    assert item.root.data.text == "hello"


def test_thinking_round_trip():
    item = ThreadItemModel.model_validate(_base_kwargs(kind="thinking", data={"text": "let me think"}))
    assert isinstance(item.root, ThinkingItem)
    assert item.root.data.text == "let me think"


def test_server_tool_use_round_trip():
    item = ThreadItemModel.model_validate(
        _base_kwargs(kind="server_tool_use", data={"tool_name": "web_search", "input": {}})
    )
    assert isinstance(item.root, ServerToolUseItem)
    assert item.root.data.tool_name == "web_search"


def test_citation_round_trip():
    item = ThreadItemModel.model_validate(
        _base_kwargs(kind="citation", data={"url": "https://example.com", "title": "Example", "snippet": "text"})
    )
    assert isinstance(item.root, CitationItem)
    assert item.root.data.url == "https://example.com"


def test_memory_pill_round_trip():
    item = ThreadItemModel.model_validate(_base_kwargs(kind="memory_pill", data={"count": 3}))
    assert isinstance(item.root, MemoryPillItem)
    assert item.root.data.count == 3


def test_turn_end_rejects_invalid_reason():
    with pytest.raises(ValidationError):
        TurnEndItem(**_base_kwargs(kind="turn_end", data={"reason": "timeout"}))
