from unittest.mock import MagicMock, patch

from ai_portal.workers.memory.extractor import MemoryDelta, MemoryUpdate, extract_user_memories


def _mock_existing(mem_id: int, content: str) -> MagicMock:
    m = MagicMock()
    m.id = mem_id
    m.content = content
    m.is_active = True
    return m


def test_extract_adds_new_memories():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = MemoryDelta(add=["Prefers Python", "Works on AI portal"])
        extract_user_memories(user_id=1, user_message="I prefer Python", assistant_message="Got it!", db=db)
    assert db.add.call_count == 2
    db.commit.assert_called_once()


def test_extract_updates_existing_memory():
    existing = _mock_existing(5, "User is a junior engineer")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [existing]
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = MemoryDelta(
            update=[MemoryUpdate(id=5, content="User is a senior data engineer")]
        )
        extract_user_memories(user_id=1, user_message="...", assistant_message="...", db=db)
    assert existing.content == "User is a senior data engineer"
    db.commit.assert_called_once()


def test_extract_removes_outdated_memory():
    existing = _mock_existing(3, "User uses Windows")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [existing]
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = MemoryDelta(remove=[3])
        extract_user_memories(user_id=1, user_message="...", assistant_message="...", db=db)
    assert existing.is_active is False
    db.commit.assert_called_once()


def test_extract_empty_delta_does_nothing():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = MemoryDelta()
        extract_user_memories(user_id=1, user_message="Hello", assistant_message="Hi!", db=db)
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_extract_ignores_invalid_update_id():
    existing = _mock_existing(1, "Some fact")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [existing]
    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = MemoryDelta(
            update=[MemoryUpdate(id=999, content="Ghost")]
        )
        extract_user_memories(user_id=1, user_message="...", assistant_message="...", db=db)
    assert existing.content == "Some fact"
