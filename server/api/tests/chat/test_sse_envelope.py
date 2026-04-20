import uuid
from datetime import datetime, timezone

from ai_portal.chat.sse import SseEvent, SseItemEvent, SseErrorEvent, SseDoneEvent


def test_item_event_roundtrip():
    payload = {
        "event_type": "item",
        "item": {
            "id": 1, "thread_id": 1, "turn_id": str(uuid.uuid4()),
            "kind": "assistant_text", "status": "streaming",
            "role": "assistant", "cost_estimated": False,
            "data": {"text": "hi"}, "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    event = SseEvent.model_validate(payload)
    assert isinstance(event.root, SseItemEvent)
    assert event.root.item.root.kind == "assistant_text"


def test_error_event_roundtrip():
    event = SseEvent.model_validate({
        "event_type": "error",
        "error": {"code": "E_QUOTA", "message": "over"},
    })
    assert isinstance(event.root, SseErrorEvent)


def test_done_event_roundtrip():
    event = SseEvent.model_validate({"event_type": "done"})
    assert isinstance(event.root, SseDoneEvent)
