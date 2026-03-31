from ai_portal.api.conversations import _should_summarize, _slice_window_messages


def test_should_summarize_at_window_boundary():
    assert _should_summarize(message_count=30, window_size=30) is True
    assert _should_summarize(message_count=60, window_size=30) is True
    assert _should_summarize(message_count=31, window_size=30) is False


def test_should_summarize_zero_messages():
    assert _should_summarize(message_count=0, window_size=30) is False


def test_slice_window_returns_last_n():
    messages = [{"role": "user", "content": str(i)} for i in range(50)]
    sliced = _slice_window_messages(messages, window_size=30)
    assert len(sliced) == 30
    assert sliced[0]["content"] == "20"


def test_slice_window_short_list():
    messages = [{"role": "user", "content": str(i)} for i in range(10)]
    sliced = _slice_window_messages(messages, window_size=30)
    assert len(sliced) == 10
