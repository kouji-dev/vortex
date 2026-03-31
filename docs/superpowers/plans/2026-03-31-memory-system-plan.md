# Memory System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two memory layers to the portal: a conversation sliding window with cumulative summarization (transparent to users, reduces token cost), and user profile memories (persistent facts extracted automatically or added manually, injected into every conversation).

**Architecture:** Conversation memory uses a `summary` field on `ChatConversation` — the last N messages are passed in full, older messages are replaced by a cumulative summary updated by a background worker. User memories live in a `user_memories` table, injected as a block in the system prompt, managed via CRUD API and a dedicated frontend page.

**Tech Stack:** Python/FastAPI backend, SQLAlchemy + Postgres, background task queue (Celery or equivalent), React + TanStack Router + TanStack Query frontend, Tailwind CSS, lucide-react icons.

---

## File Map

### New files
- `backend/alembic/versions/018_conversation_memory.py`
- `backend/alembic/versions/019_user_memories.py`
- `backend/src/ai_portal/models/memory.py` — `UserMemory` model
- `backend/src/ai_portal/workers/memory/__init__.py`
- `backend/src/ai_portal/workers/memory/summarizer.py`
- `backend/src/ai_portal/workers/memory/extractor.py`
- `backend/src/ai_portal/api/memories.py` — CRUD endpoints
- `frontend/src/hooks/useMemoriesQuery.ts`
- `frontend/src/components/memories/MemoriesPage.tsx`
- `frontend/src/routes/memories/index.tsx`

### Modified files
- `backend/src/ai_portal/config.py` — `conversation_window_size`, `conversation_inactivity_summary_hours`
- `backend/src/ai_portal/models/chat.py` — `summary`, `last_message_at` on `ChatConversation`
- `backend/src/ai_portal/models/__init__.py` — export `UserMemory`
- `backend/src/ai_portal/api/conversations.py` — window slicing, trigger enqueue, profile memory injection
- `backend/src/ai_portal/main.py` — register memories router
- `frontend/src/lib/queryKeys.ts` — `memories` key
- `frontend/src/components/layout/AppSidebar.tsx` — Memories nav link
- `frontend/src/components/chat/ConversationThreadPage.tsx` — memories active indicator
- `frontend/src/components/home/HomePage.tsx` — Memories feature card

---

## Phase 1 — Conversation Sliding Window

### Task 1: Config additions

**Files:**
- Modify: `backend/src/ai_portal/config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_memory.py
from ai_portal.config import Settings


def test_conversation_memory_defaults():
    s = Settings()
    assert s.conversation_window_size == 30
    assert s.conversation_inactivity_summary_hours == 1


def test_window_size_env_override(monkeypatch):
    monkeypatch.setenv("CONVERSATION_WINDOW_SIZE", "50")
    s = Settings()
    assert s.conversation_window_size == 50
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_config_memory.py -v
```
Expected: `AttributeError: 'Settings' object has no attribute 'conversation_window_size'`

- [ ] **Step 3: Add settings to `config.py`**

Add after the RAG settings (after `rag_max_tool_iterations`):

```python
    # Conversation memory
    conversation_window_size: int = Field(
        default=30,
        validation_alias=AliasChoices("CONVERSATION_WINDOW_SIZE"),
    )
    conversation_inactivity_summary_hours: int = Field(
        default=1,
        validation_alias=AliasChoices("CONVERSATION_INACTIVITY_SUMMARY_HOURS"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_config_memory.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/config.py backend/tests/test_config_memory.py
git commit -m "feat(config): add conversation memory window settings"
```

---

### Task 2: DB migration — ChatConversation summary + last_message_at

**Files:**
- Create: `backend/alembic/versions/018_conversation_memory.py`

- [ ] **Step 1: Create migration**

```python
# backend/alembic/versions/018_conversation_memory.py
"""Add summary and last_message_at to chat_conversations

Revision ID: 018
Revises: 017
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_conversations",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "chat_conversations",
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_conversations", "last_message_at")
    op.drop_column("chat_conversations", "summary")
```

- [ ] **Step 2: Run migration**

```
cd backend && alembic upgrade head
```
Expected: `Running upgrade 017 -> 018`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/018_conversation_memory.py
git commit -m "feat(db): add summary and last_message_at to chat_conversations"
```

---

### Task 3: Update ChatConversation model

**Files:**
- Modify: `backend/src/ai_portal/models/chat.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_chat_model_memory_fields.py
from ai_portal.models.chat import ChatConversation


def test_chat_conversation_has_summary_field():
    c = ChatConversation()
    assert hasattr(c, "summary")


def test_chat_conversation_has_last_message_at():
    c = ChatConversation()
    assert hasattr(c, "last_message_at")
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_chat_model_memory_fields.py -v
```
Expected: `AttributeError`

- [ ] **Step 3: Read current `models/chat.py` to find `ChatConversation`**

```
cd backend && grep -n "class ChatConversation\|summary\|last_message" src/ai_portal/models/chat.py
```

- [ ] **Step 4: Add fields to `ChatConversation`**

Find the `ChatConversation` class and add after `created_at`:

```python
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Make sure `Text` and `DateTime` are imported (they should be already; add if missing):
```python
from sqlalchemy import DateTime, ForeignKey, String, Text, func
```

- [ ] **Step 5: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_chat_model_memory_fields.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/models/chat.py backend/tests/test_chat_model_memory_fields.py
git commit -m "feat(models): add summary and last_message_at to ChatConversation"
```

---

### Task 4: Conversation summarizer worker

**Files:**
- Create: `backend/src/ai_portal/workers/memory/__init__.py`
- Create: `backend/src/ai_portal/workers/memory/summarizer.py`

- [ ] **Step 1: Create `__init__.py`**

```bash
mkdir -p backend/src/ai_portal/workers/memory
touch backend/src/ai_portal/workers/memory/__init__.py
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_memory_summarizer.py
from unittest.mock import MagicMock, patch

from ai_portal.workers.memory.summarizer import summarize_conversation


def test_summarize_creates_summary(monkeypatch):
    db = MagicMock()
    conv = MagicMock()
    conv.id = 1
    conv.summary = None
    conv.settings = None
    db.get.return_value = conv

    # Mock messages outside window
    old_messages = [MagicMock(role="user", content="Hello"), MagicMock(role="assistant", content="Hi")]
    db.scalars.return_value.all.return_value = old_messages

    with patch("ai_portal.workers.memory.summarizer._call_summary_llm") as mock_llm:
        mock_llm.return_value = "User greeted the assistant."
        summarize_conversation(1, window_size=30, db=db)

    assert conv.summary == "User greeted the assistant."
    db.commit.assert_called()


def test_summarize_skips_if_not_enough_messages():
    db = MagicMock()
    conv = MagicMock()
    conv.id = 1
    conv.summary = None
    db.get.return_value = conv
    db.scalars.return_value.all.return_value = []  # no messages outside window

    with patch("ai_portal.workers.memory.summarizer._call_summary_llm") as mock_llm:
        summarize_conversation(1, window_size=30, db=db)
        mock_llm.assert_not_called()


def test_summarize_unknown_conversation():
    db = MagicMock()
    db.get.return_value = None
    # Should not raise
    summarize_conversation(999, window_size=30, db=db)
```

- [ ] **Step 3: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_memory_summarizer.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 4: Create `summarizer.py`**

```python
# backend/src/ai_portal/workers/memory/summarizer.py
"""Conversation summarization worker.

Summarizes messages outside the sliding window into a cumulative summary
stored on ChatConversation.summary.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.chat import ChatConversation, ChatMessage

logger = logging.getLogger(__name__)


def summarize_conversation(
    conversation_id: int,
    *,
    window_size: int | None = None,
    db: Session | None = None,
) -> None:
    """Summarize messages outside the sliding window. Fire-and-forget."""
    settings = get_settings()
    win = window_size or settings.conversation_window_size
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        conv = db.get(ChatConversation, conversation_id)
        if conv is None:
            return

        # Get total message count and find cutoff ID
        all_msg_ids = list(db.scalars(
            select(ChatMessage.id)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id)
        ).all())

        if len(all_msg_ids) <= win:
            # Nothing outside the window yet
            return

        cutoff_id = all_msg_ids[-(win)]  # first ID inside the window

        # Messages outside the window (to summarize)
        outside_messages = list(db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.id < cutoff_id,
            )
            .order_by(ChatMessage.id)
        ).all())

        if not outside_messages:
            return

        new_summary = _call_summary_llm(
            existing_summary=conv.summary,
            messages=outside_messages,
            settings=settings,
        )

        if new_summary:
            conv.summary = new_summary
            db.commit()

    except Exception:
        logger.exception("summarize_conversation_failed", extra={"conversation_id": conversation_id})
    finally:
        if own_db:
            db.close()


def _call_summary_llm(
    *,
    existing_summary: str | None,
    messages: list[ChatMessage],
    settings,
) -> str | None:
    """Call a fast LLM to produce a cumulative summary."""
    try:
        from ai_portal.services.llm_providers import get_chat_provider

        transcript_parts = []
        if existing_summary:
            transcript_parts.append(f"[Previous summary: {existing_summary}]")
        for msg in messages:
            transcript_parts.append(f"{msg.role.upper()}: {msg.content}")
        transcript = "\n".join(transcript_parts)

        prompt = (
            "Summarize the conversation so far, incorporating any previous summary. "
            "Be concise. Preserve: key decisions, facts established, user goals, "
            "unresolved questions. Discard: pleasantries, repetition.\n\n"
            + transcript
        )

        provider = get_chat_provider(settings)
        result = provider.complete(
            messages=[{"role": "user", "content": prompt}],
            model=settings.chat_default_api_model,
        )
        return result.strip() if result else None
    except Exception:
        logger.exception("summary_llm_call_failed")
        return None
```

Note: `get_chat_provider` and its `complete()` method need to exist in `services/llm_providers/`. Check what's available in that module. If only streaming is available, collect all deltas and join them. Adjust the call to match the actual provider interface.

- [ ] **Step 5: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_memory_summarizer.py -v
```
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/workers/memory/ backend/tests/test_memory_summarizer.py
git commit -m "feat(workers): add conversation summarizer worker"
```

---

### Task 5: Wire sliding window + triggers in conversations.py

**Files:**
- Modify: `backend/src/ai_portal/api/conversations.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_conversation_window.py
from ai_portal.api.conversations import _should_summarize, _slice_window_messages


def test_should_summarize_at_window_boundary():
    assert _should_summarize(message_count=30, window_size=30) is True
    assert _should_summarize(message_count=60, window_size=30) is True
    assert _should_summarize(message_count=31, window_size=30) is False
    assert _should_summarize(message_count=0, window_size=30) is False


def test_slice_window_returns_last_n():
    messages = [{"role": "user", "content": str(i)} for i in range(50)]
    sliced = _slice_window_messages(messages, window_size=30)
    assert len(sliced) == 30
    assert sliced[0]["content"] == "20"  # first of last 30


def test_slice_window_short_list():
    messages = [{"role": "user", "content": str(i)} for i in range(10)]
    sliced = _slice_window_messages(messages, window_size=30)
    assert len(sliced) == 10  # all messages returned if fewer than window
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_conversation_window.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Add helper functions to `conversations.py`**

Add near the top of the file (after imports):

```python
from datetime import datetime, timedelta, timezone


def _should_summarize(*, message_count: int, window_size: int) -> bool:
    """Return True when the total message count hits a window boundary."""
    return message_count > 0 and message_count % window_size == 0


def _slice_window_messages(
    messages: list[dict],
    *,
    window_size: int,
) -> list[dict]:
    """Return only the last window_size messages."""
    return messages[-window_size:] if len(messages) > window_size else messages
```

- [ ] **Step 4: Apply window slicing in the stream endpoint**

In the stream endpoint, find where `prior` is built from `prior_rows`:

```python
    prior: list[dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in prior_rows
    ]
```

Replace with:

```python
    all_prior: list[dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in prior_rows
    ]
    prior = _slice_window_messages(all_prior, window_size=settings.conversation_window_size)

    # Prepend conversation summary if it exists (covers messages outside the window)
    if conv.summary:
        system_parts_summary = f"Earlier in this conversation:\n{conv.summary}"
    else:
        system_parts_summary = None
```

Then in the `system_parts` list, add the summary after the base prompt and memories:

```python
    if system_parts_summary:
        system_parts.append(system_parts_summary)
```

- [ ] **Step 5: Update `last_message_at` on every message save**

Find where `user_msg` is saved and add:

```python
    conv.last_message_at = datetime.now(tz=timezone.utc)
    db.commit()
```

- [ ] **Step 6: Enqueue summarization after assistant response is saved**

In `gen()`, after `db.commit()` on the assistant reply, add:

```python
        # Check summarization triggers (fire-and-forget)
        total_msgs = db.scalar(
            select(func.count()).where(ChatMessage.conversation_id == conv.id)
        )
        if _should_summarize(message_count=total_msgs, window_size=settings.conversation_window_size):
            from ai_portal.workers.memory.summarizer import summarize_conversation
            # Enqueue as background task — for now call directly in thread
            import threading
            threading.Thread(
                target=summarize_conversation,
                args=(conv.id,),
                daemon=True,
            ).start()
```

Note: Replace `threading.Thread` with your actual task queue enqueue call (Celery `delay()`, FastAPI `BackgroundTasks`, etc.) once the task queue integration is confirmed. The threading approach works for development.

- [ ] **Step 7: Run tests**

```
cd backend && python -m pytest tests/test_conversation_window.py tests/test_conversations_api.py -v
```
Expected: All PASSED

- [ ] **Step 8: Commit**

```bash
git add backend/src/ai_portal/api/conversations.py backend/tests/test_conversation_window.py
git commit -m "feat(chat): add sliding window message slicing and summarization triggers"
```

---

## Phase 2 — User Profile Memories

### Task 6: DB migration — user_memories table

**Files:**
- Create: `backend/alembic/versions/019_user_memories.py`

- [ ] **Step 1: Create migration**

```python
# backend/alembic/versions/019_user_memories.py
"""Create user_memories table

Revision ID: 019
Revises: 018
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_memories")
```

- [ ] **Step 2: Run migration**

```
cd backend && alembic upgrade head
```
Expected: `Running upgrade 018 -> 019`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/019_user_memories.py
git commit -m "feat(db): create user_memories table"
```

---

### Task 7: UserMemory model

**Files:**
- Create: `backend/src/ai_portal/models/memory.py`
- Modify: `backend/src/ai_portal/models/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_model.py
from ai_portal.models.memory import UserMemory


def test_user_memory_has_required_fields():
    m = UserMemory(user_id=1, content="Prefers Python", source="manual", is_active=True)
    assert m.user_id == 1
    assert m.content == "Prefers Python"
    assert m.source == "manual"
    assert m.is_active is True
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_memory_model.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `models/memory.py`**

```python
# backend/src/ai_portal/models/memory.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.db.base import Base


class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Export from `models/__init__.py`**

Open `backend/src/ai_portal/models/__init__.py` and add:

```python
from ai_portal.models.memory import UserMemory
```

- [ ] **Step 5: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_memory_model.py -v
```
Expected: 1 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/models/memory.py backend/src/ai_portal/models/__init__.py backend/tests/test_memory_model.py
git commit -m "feat(models): add UserMemory model"
```

---

### Task 8: Memory extractor worker

**Files:**
- Create: `backend/src/ai_portal/workers/memory/extractor.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_memory_extractor.py
from unittest.mock import MagicMock, patch

from ai_portal.workers.memory.extractor import extract_user_memories


def test_extract_saves_new_memories():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []  # no existing memories

    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = ["Prefers Python over JS", "Works on an AI portal"]
        extract_user_memories(
            user_id=1,
            user_message="I prefer Python",
            assistant_message="Got it!",
            db=db,
        )

    assert db.add.call_count == 2


def test_extract_skips_duplicate_memories():
    db = MagicMock()
    existing = MagicMock()
    existing.content = "Prefers Python over JS"
    db.scalars.return_value.all.return_value = [existing]

    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = ["Prefers Python over JS"]  # exact duplicate
        extract_user_memories(
            user_id=1,
            user_message="I prefer Python",
            assistant_message="Got it!",
            db=db,
        )

    db.add.assert_not_called()


def test_extract_empty_result_does_nothing():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    with patch("ai_portal.workers.memory.extractor._call_extraction_llm") as mock_llm:
        mock_llm.return_value = []
        extract_user_memories(
            user_id=1,
            user_message="Hello",
            assistant_message="Hi there!",
            db=db,
        )

    db.add.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_memory_extractor.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `extractor.py`**

```python
# backend/src/ai_portal/workers/memory/extractor.py
"""User profile memory extraction worker.

After each assistant response, extracts persistent facts about the user
and saves them as UserMemory rows.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.memory import UserMemory

logger = logging.getLogger(__name__)


def extract_user_memories(
    user_id: int,
    *,
    user_message: str,
    assistant_message: str,
    db: Session | None = None,
) -> None:
    """Extract and save new profile memories from an exchange. Fire-and-forget."""
    settings = get_settings()
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        facts = _call_extraction_llm(
            user_message=user_message,
            assistant_message=assistant_message,
            settings=settings,
        )
        if not facts:
            return

        # Fetch existing memory contents for deduplication
        existing = list(db.scalars(
            select(UserMemory.content).where(UserMemory.user_id == user_id)
        ).all())
        existing_lower = {c.lower().strip() for c in existing}

        for fact in facts:
            fact = fact.strip()
            if not fact:
                continue
            # Simple exact-match dedup (case-insensitive)
            if fact.lower() in existing_lower:
                continue
            db.add(UserMemory(
                user_id=user_id,
                content=fact,
                source="auto",
                is_active=True,
            ))

        db.commit()

    except Exception:
        logger.exception("extract_user_memories_failed", extra={"user_id": user_id})
    finally:
        if own_db:
            db.close()


def _call_extraction_llm(
    *,
    user_message: str,
    assistant_message: str,
    settings,
) -> list[str]:
    """Call a fast LLM to extract user facts. Returns list of fact strings."""
    try:
        from ai_portal.services.llm_providers import get_chat_provider

        prompt = (
            "Extract any persistent facts about the user from this exchange. "
            "Return a JSON array of strings. Return [] if nothing notable. "
            "Only include facts useful across future conversations: preferences, role, "
            "tools they use, constraints they mentioned. Do not include one-off questions.\n\n"
            f"USER: {user_message}\n"
            f"ASSISTANT: {assistant_message}"
        )

        provider = get_chat_provider(settings)
        raw = provider.complete(
            messages=[{"role": "user", "content": prompt}],
            model=settings.chat_default_api_model,
        )
        if not raw:
            return []

        # Parse JSON array from response
        raw = raw.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []
        return json.loads(raw[start : end + 1])

    except Exception:
        logger.exception("extraction_llm_call_failed")
        return []
```

Note: `get_chat_provider` and its `complete()` method — check `services/llm_providers/` for the actual interface. Adapt the call accordingly if the method name differs.

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_memory_extractor.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/workers/memory/extractor.py backend/tests/test_memory_extractor.py
git commit -m "feat(workers): add user memory extractor worker"
```

---

### Task 9: Memories CRUD API

**Files:**
- Create: `backend/src/ai_portal/api/memories.py`
- Modify: `backend/src/ai_portal/main.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_memories_api.py
from fastapi.testclient import TestClient


def test_list_memories_empty(client: TestClient, auth_headers):
    res = client.get("/api/users/me/memories", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_create_memory(client: TestClient, auth_headers):
    res = client.post(
        "/api/users/me/memories",
        json={"content": "Prefers Python"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["content"] == "Prefers Python"
    assert data["source"] == "manual"
    assert data["is_active"] is True


def test_update_memory_toggle(client: TestClient, auth_headers):
    # Create first
    res = client.post(
        "/api/users/me/memories",
        json={"content": "Works in React"},
        headers=auth_headers,
    )
    mem_id = res.json()["id"]

    # Toggle off
    res = client.patch(
        f"/api/users/me/memories/{mem_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_delete_memory(client: TestClient, auth_headers):
    res = client.post(
        "/api/users/me/memories",
        json={"content": "To delete"},
        headers=auth_headers,
    )
    mem_id = res.json()["id"]

    res = client.delete(f"/api/users/me/memories/{mem_id}", headers=auth_headers)
    assert res.status_code == 204

    # Verify gone
    res = client.get("/api/users/me/memories", headers=auth_headers)
    ids = [m["id"] for m in res.json()]
    assert mem_id not in ids


def test_cannot_access_other_users_memory(client: TestClient, auth_headers):
    # Creating memory under user 1, trying to delete as user 1 but with wrong id
    res = client.delete("/api/users/me/memories/99999", headers=auth_headers)
    assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_memories_api.py -v
```
Expected: `404 Not Found` (endpoint doesn't exist yet)

- [ ] **Step 3: Create `api/memories.py`**

```python
# backend/src/ai_portal/api/memories.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_db, require_user
from ai_portal.models.memory import UserMemory
from ai_portal.models.user import User

router = APIRouter()


class MemoryOut(BaseModel):
    id: int
    content: str
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateMemoryBody(BaseModel):
    content: str


class UpdateMemoryBody(BaseModel):
    content: str | None = None
    is_active: bool | None = None


@router.get("/users/me/memories", response_model=list[MemoryOut])
def list_memories(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[UserMemory]:
    return list(db.scalars(
        select(UserMemory)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.is_active.desc(), UserMemory.created_at.desc())
    ).all())


@router.post("/users/me/memories", response_model=MemoryOut, status_code=201)
def create_memory(
    body: CreateMemoryBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> UserMemory:
    mem = UserMemory(
        user_id=user.id,
        content=body.content.strip(),
        source="manual",
        is_active=True,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


@router.patch("/users/me/memories/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    body: UpdateMemoryBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> UserMemory:
    mem = db.scalars(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user.id,
        )
    ).first()
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    if body.content is not None:
        mem.content = body.content.strip()
    if body.is_active is not None:
        mem.is_active = body.is_active
    db.commit()
    db.refresh(mem)
    return mem


@router.delete("/users/me/memories/{memory_id}", status_code=204)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    mem = db.scalars(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user.id,
        )
    ).first()
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(mem)
    db.commit()
```

- [ ] **Step 4: Register router in `main.py`**

Open `backend/src/ai_portal/main.py` and add:

```python
from ai_portal.api.memories import router as memories_router

# In the app setup, alongside other router includes:
app.include_router(memories_router, prefix="/api")
```

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_memories_api.py -v
```
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/api/memories.py backend/src/ai_portal/main.py backend/tests/test_memories_api.py
git commit -m "feat(api): add user memories CRUD endpoints"
```

---

### Task 10: Inject profile memories into system prompt

**Files:**
- Modify: `backend/src/ai_portal/api/conversations.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_injection.py
from unittest.mock import MagicMock, patch
from ai_portal.api.conversations import _build_memory_block


def test_memory_block_with_active_memories():
    memories = [
        MagicMock(content="Prefers Python", is_active=True),
        MagicMock(content="Works at Acme", is_active=True),
    ]
    block = _build_memory_block(memories)
    assert "Prefers Python" in block
    assert "Works at Acme" in block
    assert "What you know about this user" in block


def test_memory_block_empty_when_no_active():
    block = _build_memory_block([])
    assert block == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_memory_injection.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Add `_build_memory_block` to `conversations.py`**

```python
def _build_memory_block(memories: list) -> str:
    """Format active user memories as a system prompt block."""
    active = [m for m in memories if m.is_active]
    if not active:
        return ""
    lines = "\n".join(f"- {m.content}" for m in active)
    return f"What you know about this user:\n{lines}"
```

- [ ] **Step 4: Load and inject memories in the stream endpoint**

In the stream endpoint, after loading `kb_ids`, add:

```python
    from ai_portal.models.memory import UserMemory as UserMemoryModel
    active_memories = list(db.scalars(
        select(UserMemoryModel)
        .where(UserMemoryModel.user_id == current_user.id, UserMemoryModel.is_active == True)
        .order_by(UserMemoryModel.created_at)
    ).all())
    memory_block = _build_memory_block(active_memories)
```

In the `system_parts` construction, add the memory block after the base prompt:

```python
    system_parts: list[str] = []
    if assistant is not None:
        system_parts.append(assistant.system_prompt.strip())
    else:
        system_parts.append(settings.default_system_prompt.strip())

    if memory_block:
        system_parts.append(memory_block)

    if system_parts_summary:  # conversation summary from Task 5
        system_parts.append(system_parts_summary)
    # ... rest of system_parts (RAG tool instructions, capabilities)
```

- [ ] **Step 5: Enqueue memory extraction after assistant reply**

In `gen()`, after saving the assistant reply, add (alongside the summarization trigger):

```python
        # Enqueue memory extraction (fire-and-forget)
        import threading
        from ai_portal.workers.memory.extractor import extract_user_memories
        threading.Thread(
            target=extract_user_memories,
            kwargs={
                "user_id": current_user.id,
                "user_message": user_content,
                "assistant_message": reply,
            },
            daemon=True,
        ).start()
```

Note: Replace `threading.Thread` with your actual task queue when available.

- [ ] **Step 6: Run tests**

```
cd backend && python -m pytest tests/test_memory_injection.py tests/test_chat_api.py -v
```
Expected: All PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/src/ai_portal/api/conversations.py backend/tests/test_memory_injection.py
git commit -m "feat(chat): inject user profile memories into system prompt"
```

---

## Phase 3 — Frontend

### Task 11: queryKeys + useMemoriesQuery

**Files:**
- Modify: `frontend/src/lib/queryKeys.ts`
- Create: `frontend/src/hooks/useMemoriesQuery.ts`

- [ ] **Step 1: Add `memories` key to `queryKeys.ts`**

```typescript
// frontend/src/lib/queryKeys.ts
export const queryKeys = {
  // ... existing keys ...
  memories: () => ['memories'] as const,
}
```

- [ ] **Step 2: Create `useMemoriesQuery.ts`**

```typescript
// frontend/src/hooks/useMemoriesQuery.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getApiBase } from '@/lib/api-base'
import { authorizedFetch } from '@/lib/authorizedFetch'
import { queryKeys } from '@/lib/queryKeys'

export interface Memory {
  id: number
  content: string
  source: 'auto' | 'manual'
  is_active: boolean
  created_at: string
  updated_at: string
}

export function useMemoriesQuery() {
  const apiBase = getApiBase()
  return useQuery({
    queryKey: queryKeys.memories(),
    queryFn: async (): Promise<Memory[]> => {
      const res = await authorizedFetch(`${apiBase}/api/users/me/memories`)
      if (!res.ok) throw new Error(`Failed to fetch memories: ${res.status}`)
      return res.json()
    },
  })
}

export function useCreateMemoryMutation() {
  const apiBase = getApiBase()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (content: string): Promise<Memory> => {
      const res = await authorizedFetch(`${apiBase}/api/users/me/memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      if (!res.ok) throw new Error(`Failed to create memory: ${res.status}`)
      return res.json()
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.memories() }),
  })
}

export function useUpdateMemoryMutation() {
  const apiBase = getApiBase()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      content,
      is_active,
    }: {
      id: number
      content?: string
      is_active?: boolean
    }): Promise<Memory> => {
      const res = await authorizedFetch(`${apiBase}/api/users/me/memories/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, is_active }),
      })
      if (!res.ok) throw new Error(`Failed to update memory: ${res.status}`)
      return res.json()
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.memories() }),
  })
}

export function useDeleteMemoryMutation() {
  const apiBase = getApiBase()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number): Promise<void> => {
      const res = await authorizedFetch(`${apiBase}/api/users/me/memories/${id}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(`Failed to delete memory: ${res.status}`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.memories() }),
  })
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/queryKeys.ts frontend/src/hooks/useMemoriesQuery.ts
git commit -m "feat(frontend): add memories query key and useMemoriesQuery hooks"
```

---

### Task 12: MemoriesPage component + route

**Files:**
- Create: `frontend/src/components/memories/MemoriesPage.tsx`
- Create: `frontend/src/routes/memories/index.tsx`

- [ ] **Step 1: Create `MemoriesPage.tsx`**

```tsx
// frontend/src/components/memories/MemoriesPage.tsx
import React from 'react'
import { Brain, Plus, Trash2, Pencil, Check, X } from 'lucide-react'
import {
  useMemoriesQuery,
  useCreateMemoryMutation,
  useUpdateMemoryMutation,
  useDeleteMemoryMutation,
  type Memory,
} from '@/hooks/useMemoriesQuery'

export function MemoriesPage() {
  const { data: memories = [], isLoading } = useMemoriesQuery()
  const createMutation = useCreateMemoryMutation()
  const updateMutation = useUpdateMemoryMutation()
  const deleteMutation = useDeleteMemoryMutation()

  const [addingNew, setAddingNew] = React.useState(false)
  const [newContent, setNewContent] = React.useState('')
  const [editingId, setEditingId] = React.useState<number | null>(null)
  const [editContent, setEditContent] = React.useState('')

  function handleAdd() {
    if (!newContent.trim()) return
    createMutation.mutate(newContent.trim(), {
      onSuccess: () => {
        setNewContent('')
        setAddingNew(false)
      },
    })
  }

  function handleEditStart(mem: Memory) {
    setEditingId(mem.id)
    setEditContent(mem.content)
  }

  function handleEditSave(id: number) {
    updateMutation.mutate({ id, content: editContent.trim() }, {
      onSuccess: () => setEditingId(null),
    })
  }

  function handleToggle(mem: Memory) {
    updateMutation.mutate({ id: mem.id, is_active: !mem.is_active })
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={20} />
          <h1 className="text-xl font-semibold">Memories</h1>
        </div>
        <button
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          onClick={() => setAddingNew(true)}
        >
          <Plus size={14} />
          Add
        </button>
      </div>

      {addingNew && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border p-3">
          <input
            autoFocus
            className="flex-1 bg-transparent text-sm outline-none"
            placeholder="Enter a memory…"
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd()
              if (e.key === 'Escape') setAddingNew(false)
            }}
          />
          <button onClick={handleAdd} className="text-primary hover:opacity-70">
            <Check size={16} />
          </button>
          <button onClick={() => setAddingNew(false)} className="text-muted-foreground hover:opacity-70">
            <X size={16} />
          </button>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : memories.length === 0 ? (
        <p className="text-sm text-muted-foreground">No memories yet. The assistant will learn about you over time.</p>
      ) : (
        <ul className="space-y-2">
          {memories.map((mem) => (
            <li
              key={mem.id}
              className={`flex items-start gap-3 rounded-lg border p-3 transition-opacity ${!mem.is_active ? 'opacity-50' : ''}`}
            >
              {/* Active toggle */}
              <button
                className={`mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 transition-colors ${mem.is_active ? 'border-primary bg-primary' : 'border-muted-foreground'}`}
                title={mem.is_active ? 'Deactivate' : 'Activate'}
                onClick={() => handleToggle(mem)}
              />

              {/* Content (editable) */}
              <div className="flex-1">
                {editingId === mem.id ? (
                  <div className="flex items-center gap-2">
                    <input
                      autoFocus
                      className="flex-1 bg-transparent text-sm outline-none"
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleEditSave(mem.id)
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                    />
                    <button onClick={() => handleEditSave(mem.id)} className="text-primary hover:opacity-70">
                      <Check size={14} />
                    </button>
                    <button onClick={() => setEditingId(null)} className="text-muted-foreground hover:opacity-70">
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <p
                    className="cursor-text text-sm"
                    onClick={() => handleEditStart(mem)}
                  >
                    {mem.content}
                  </p>
                )}
                <span className="mt-0.5 inline-block rounded bg-muted px-1 py-0.5 text-xs text-muted-foreground">
                  {mem.source}
                </span>
              </div>

              {/* Delete */}
              <button
                className="shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => deleteMutation.mutate(mem.id)}
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create route file**

```tsx
// frontend/src/routes/memories/index.tsx
import { createFileRoute } from '@tanstack/react-router'
import { MemoriesPage } from '@/components/memories/MemoriesPage'

export const Route = createFileRoute('/memories/')({
  component: MemoriesPage,
})
```

- [ ] **Step 3: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/memories/ frontend/src/routes/memories/
git commit -m "feat(frontend): add MemoriesPage component and route"
```

---

### Task 13: AppSidebar — Memories nav link

**Files:**
- Modify: `frontend/src/components/layout/AppSidebar.tsx`

- [ ] **Step 1: Read current sidebar to find nav link pattern**

```
cd frontend && cat src/components/layout/AppSidebar.tsx
```

- [ ] **Step 2: Add Memories link**

Find the nav section with the existing links (Dashboard, Chat, Knowledge Bases). Add Memories between Chat and Knowledge Bases:

```tsx
import { Brain } from 'lucide-react'  // add to existing lucide import

// In the nav links list:
<Link
  to="/memories"
  className={/* same className pattern as other links */}
>
  <Brain size={18} />
  {!compact && <span>Memories</span>}
</Link>
```

- [ ] **Step 3: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/AppSidebar.tsx
git commit -m "feat(frontend): add Memories nav link to sidebar"
```

---

### Task 14: ConversationThreadPage — memories active indicator

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

- [ ] **Step 1: Add memories indicator to chat header**

Add import and query:

```tsx
import { Brain } from 'lucide-react'
import { useMemoriesQuery } from '@/hooks/useMemoriesQuery'
import { useNavigate } from '@tanstack/react-router'

// Inside the component:
const { data: memories = [] } = useMemoriesQuery()
const activeMemoryCount = memories.filter((m) => m.is_active).length
const navigate = useNavigate()
```

In the conversation header (find where title/delete button are rendered), add:

```tsx
{activeMemoryCount > 0 && (
  <button
    className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted"
    title={`${activeMemoryCount} memories active`}
    onClick={() => navigate({ to: '/memories' })}
  >
    <Brain size={12} />
    {activeMemoryCount}
  </button>
)}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(frontend): add memories active indicator to conversation header"
```

---

### Task 15: HomePage — Memories feature card

**Files:**
- Modify: `frontend/src/components/home/HomePage.tsx`

- [ ] **Step 1: Read current HomePage to understand FeatureCard usage**

```
cd frontend && grep -n "FeatureCard\|import" src/components/home/HomePage.tsx | head -20
```

- [ ] **Step 2: Add Memories FeatureCard**

Find the FeatureCard grid in `HomePage.tsx`. Add a Memories card alongside Chat and Knowledge Bases:

```tsx
<FeatureCard
  to="/memories"
  title="Memories"
  description="Facts the assistant knows about you, across all conversations."
/>
```

(Match the exact `FeatureCard` props used by the other cards — check the component for required props.)

- [ ] **Step 3: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/home/HomePage.tsx
git commit -m "feat(frontend): add Memories feature card to homepage"
```

---

## Final verification

- [ ] **Run full backend test suite**

```
cd backend && python -m pytest tests/ -v --tb=short
```
Expected: All tests pass

- [ ] **Run frontend build**

```
cd frontend && npm run build
```
Expected: No TypeScript or build errors

- [ ] **Smoke test memory extraction end-to-end**

Start the backend and frontend locally, have a conversation, check that:
1. Profile memories appear at `/memories` after a few turns
2. Toggling a memory off removes it from the next response's system prompt (verify via backend logs)
3. Long conversations (30+ messages) trigger summarization (verify `ChatConversation.summary` in DB)

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: memory system complete — sliding window + user profile memories"
```
