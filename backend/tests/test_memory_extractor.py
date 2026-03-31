from unittest.mock import MagicMock, patch

from ai_portal.workers.memory.extractor import extract_user_memories


def test_extract_saves_new_memories():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = ["Prefers Python", "Works on AI portal"]
        extract_user_memories(user_id=1, user_message="I prefer Python", assistant_message="Got it!", db=db)
    assert db.add.call_count == 2


def test_extract_skips_duplicates():
    db = MagicMock()
    existing = MagicMock()
    existing.content = "Prefers Python"
    db.scalars.return_value.all.return_value = [existing]
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = ["Prefers Python"]
        extract_user_memories(user_id=1, user_message="...", assistant_message="...", db=db)
    db.add.assert_not_called()


def test_extract_empty_does_nothing():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = []
        extract_user_memories(user_id=1, user_message="Hello", assistant_message="Hi!", db=db)
    db.add.assert_not_called()
