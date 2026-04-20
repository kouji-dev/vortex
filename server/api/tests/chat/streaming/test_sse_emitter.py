# tests/chat/streaming/test_sse_emitter.py
from ai_portal.chat.sse import SseDoneEvent, SseEvent
from ai_portal.chat.streaming.sse_emitter import encode


def test_encode_done_event():
    event = SseEvent.model_validate({"event_type": "done"})
    result = encode(event)
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    assert '"event_type":"done"' in result


def test_encode_error_event():
    event = SseEvent.model_validate({"event_type": "error", "error": {"code": "E001", "message": "bad"}})
    result = encode(event)
    assert '"event_type":"error"' in result
    assert '"code":"E001"' in result
