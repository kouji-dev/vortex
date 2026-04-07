import uuid
from unittest.mock import MagicMock, patch

from ai_portal.workers.memory.extractor import extract_user_memories

_ORG = uuid.uuid4()


def _mock_system_mem(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    m.is_active = True
    m.is_system = True
    return m


def test_extract_creates_system_row_when_missing():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    with patch(
        "ai_portal.workers.memory.extractor._call_system_profile_llm"
    ) as mock_llm:
        mock_llm.return_value = "Prefers Python for tooling."
        extract_user_memories(
            user_id=1,
            org_id=_ORG,
            user_message="I prefer Python",
            assistant_message="Noted.",
            db=db,
        )
    assert db.add.call_count == 1
    added = db.add.call_args[0][0]
    assert added.is_system is True
    assert added.source == "auto"
    assert "Python" in added.content
    db.commit.assert_called_once()


def test_extract_updates_existing_system_row():
    existing = _mock_system_mem("Old profile")
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing
    with patch(
        "ai_portal.workers.memory.extractor._call_system_profile_llm"
    ) as mock_llm:
        mock_llm.return_value = "New profile text"
        extract_user_memories(
            user_id=1,
            org_id=_ORG,
            user_message="...",
            assistant_message="...",
            db=db,
        )
    assert existing.content == "New profile text"
    db.commit.assert_called_once()


def test_extract_empty_update_skips_commit():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    with patch(
        "ai_portal.workers.memory.extractor._call_system_profile_llm"
    ) as mock_llm:
        mock_llm.return_value = ""
        extract_user_memories(
            user_id=1,
            org_id=_ORG,
            user_message="Hi",
            assistant_message="Hello",
            db=db,
        )
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_extract_same_text_skips_commit():
    existing = _mock_system_mem("Unchanged")
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing
    with patch(
        "ai_portal.workers.memory.extractor._call_system_profile_llm"
    ) as mock_llm:
        mock_llm.return_value = "Unchanged"
        extract_user_memories(
            user_id=1,
            org_id=_ORG,
            user_message="x",
            assistant_message="y",
            db=db,
        )
    db.commit.assert_not_called()
