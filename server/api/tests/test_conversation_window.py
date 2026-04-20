from ai_portal.chat.context_window import should_summarize as _should_summarize, slice_window_messages as _slice_window_messages

BASE = 30
INTERVAL = 10


# -- _should_summarize ---------------------------------------------------------

def test_should_not_summarize_at_or_below_base():
    for n in range(0, BASE + 1):
        assert _should_summarize(
            message_count=n, base_window=BASE, summary_interval=INTERVAL
        ) is False


def test_should_summarize_immediately_after_base():
    assert (
        _should_summarize(
            message_count=BASE + 1, base_window=BASE, summary_interval=INTERVAL
        )
        is True
    )


def test_should_summarize_at_interval_boundaries():
    assert _should_summarize(message_count=BASE + INTERVAL, base_window=BASE, summary_interval=INTERVAL) is True
    assert _should_summarize(message_count=BASE + 2 * INTERVAL, base_window=BASE, summary_interval=INTERVAL) is True
    assert _should_summarize(message_count=BASE + 3 * INTERVAL, base_window=BASE, summary_interval=INTERVAL) is True


def test_should_not_summarize_between_intervals():
    assert _should_summarize(message_count=BASE + 5, base_window=BASE, summary_interval=INTERVAL) is False
    assert _should_summarize(message_count=BASE + INTERVAL + 3, base_window=BASE, summary_interval=INTERVAL) is False


# -- _slice_window_messages ----------------------------------------------------

def test_slice_returns_all_below_base():
    messages = [{"role": "user", "content": str(i)} for i in range(20)]
    sliced = _slice_window_messages(
        messages, base_window=BASE, summary_interval=INTERVAL, has_summary=False
    )
    assert len(sliced) == 20


def test_slice_returns_all_at_base():
    messages = [{"role": "user", "content": str(i)} for i in range(BASE)]
    sliced = _slice_window_messages(
        messages, base_window=BASE, summary_interval=INTERVAL, has_summary=False
    )
    assert len(sliced) == BASE


def test_slice_keeps_base_window_when_no_summary():
    messages = [{"role": "user", "content": str(i)} for i in range(40)]
    sliced = _slice_window_messages(
        messages, base_window=BASE, summary_interval=INTERVAL, has_summary=False
    )
    assert len(sliced) == BASE
    assert sliced[0]["content"] == "10"


def test_slice_returns_interval_when_summary_exists():
    messages = [{"role": "user", "content": str(i)} for i in range(50)]
    sliced = _slice_window_messages(
        messages, base_window=BASE, summary_interval=INTERVAL, has_summary=True
    )
    assert len(sliced) == INTERVAL
    assert sliced[0]["content"] == "40"
    assert sliced[-1]["content"] == "49"
