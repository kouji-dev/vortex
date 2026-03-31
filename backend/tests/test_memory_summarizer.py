from unittest.mock import MagicMock, patch

from ai_portal.workers.memory.summarizer import summarize_conversation


def _make_mock_message(msg_id, role, content):
    m = MagicMock()
    m.id = msg_id
    m.role = role
    m.content = content
    return m


@patch("ai_portal.workers.memory.summarizer.SessionLocal")
@patch("ai_portal.workers.memory.summarizer._call_summary_llm")
def test_summarize_creates_summary(mock_llm, mock_session_cls):
    db = MagicMock()
    mock_session_cls.return_value = db

    conv = MagicMock()
    conv.id = 1
    conv.summary = None
    conv.settings = None
    db.get.return_value = conv

    all_ids = list(range(1, 41))
    db.scalars.return_value.all.return_value = all_ids

    outside_msgs = [_make_mock_message(i, "user", f"msg {i}") for i in range(1, 11)]
    db.execute.return_value.scalars.return_value.all.return_value = outside_msgs

    mock_llm.return_value = "Summary of the conversation so far."

    summarize_conversation(1, summary_interval=10)

    mock_llm.assert_called_once()
    assert conv.summary == "Summary of the conversation so far."
    db.commit.assert_called_once()
    db.close.assert_called_once()


@patch("ai_portal.workers.memory.summarizer.SessionLocal")
@patch("ai_portal.workers.memory.summarizer._call_summary_llm")
def test_summarize_skips_if_not_enough_messages(mock_llm, mock_session_cls):
    db = MagicMock()
    mock_session_cls.return_value = db

    conv = MagicMock()
    conv.id = 1
    conv.summary = None
    db.get.return_value = conv

    all_ids = list(range(1, 11))
    db.scalars.return_value.all.return_value = all_ids

    summarize_conversation(1, summary_interval=30)

    mock_llm.assert_not_called()
    db.close.assert_called_once()


@patch("ai_portal.workers.memory.summarizer.SessionLocal")
def test_summarize_unknown_conversation(mock_session_cls):
    db = MagicMock()
    mock_session_cls.return_value = db
    db.get.return_value = None

    summarize_conversation(999, summary_interval=10)

    db.commit.assert_not_called()
    db.close.assert_called_once()
