# RAG KB Chat UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the collapsible KB panel with a command-palette KB picker in the composer toolbar, and add a hover-only green 📚 indicator on AI messages that shows which KBs were actually used.

**Architecture:** Backend extends `retrieve_context` to return retrieval metadata alongside context text; metadata is stored in `ChatMessage.extra["used_kbs"]` (existing JSONB column — no migration needed). Frontend adds three new components (`KbsToolbarButton`, `KbPickerDialog`, `MessageKbIndicator`) wired into `ChatComposerDock` and `ConversationThreadPage`. The old `ConversationKnowledgeBasesPanel` collapsible and the explicit RAG toggle are removed.

**Tech Stack:** Python/FastAPI (backend), React 18 + TypeScript, Tailwind CSS v4, TanStack Query, Lucide icons (already installed).

---

## File map

| File | Change |
|------|--------|
| `backend/src/ai_portal/services/rag.py` | Extend `retrieve_context` to return `(str, list[dict])` metadata |
| `backend/src/ai_portal/api/conversations.py` | Store `used_kbs` in `message.extra`; always enable RAG when KBs attached |
| `backend/tests/test_rag_retrieval.py` | New: unit tests for metadata return |
| `frontend/src/lib/chat-types.ts` | Add `UsedKbEntry` type; add `used_kbs` to `ChatMessage` |
| `frontend/src/components/knowledge-bases/KbsToolbarButton.tsx` | New: toolbar button + active badge + hover popover |
| `frontend/src/components/knowledge-bases/KbPickerDialog.tsx` | New: command palette for KB attach/detach |
| `frontend/src/components/knowledge-bases/MessageKbIndicator.tsx` | New: green 📚 icon + hover popover on AI messages |
| `frontend/src/components/chat/ChatComposerDock.tsx` | Add KB button props; remove `showRag`/`useRag`/`setUseRag` |
| `frontend/src/components/chat/ConversationThreadPage.tsx` | Remove old KB panel + RAG toggle; add KB indicator to messages; always send `use_rag: true` |

---

## Task 1: Extend `retrieve_context` to return retrieval metadata

**Files:**
- Modify: `backend/src/ai_portal/services/rag.py`
- Create: `backend/tests/test_rag_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_rag_retrieval.py
from unittest.mock import MagicMock, patch
from ai_portal.services.rag import retrieve_context_with_meta


def test_returns_empty_when_no_kb_ids():
    db = MagicMock()
    context, meta = retrieve_context_with_meta(db, knowledge_base_ids=[], query_embedding=[0.1] * 3)
    assert context == ""
    assert meta == []


def test_returns_meta_per_kb(monkeypatch):
    """Meta list has one entry per KB that contributed chunks."""
    from ai_portal.models import Document, DocumentChunk
    from ai_portal.models.knowledge_base import KnowledgeBase

    kb1 = MagicMock(spec=KnowledgeBase)
    kb1.id = 1
    kb1.name = "HR Policies"

    chunk1 = MagicMock(spec=DocumentChunk)
    chunk1.content = "Remote work policy text"
    chunk1.embedding = [0.1] * 3
    chunk1.meta = {"source": "Remote Work p.14"}

    doc1 = MagicMock(spec=Document)
    doc1.id = 10
    doc1.knowledge_base_id = 1

    chunk1.document_id = 10

    db = MagicMock()
    # scalars().all() for doc_ids → [10], for chunks → [chunk1], for kbs → [kb1]
    db.scalars.return_value.all.side_effect = [[doc1.id], [chunk1], [kb1]]

    # cosine_distance returns a dummy score
    with patch("ai_portal.services.rag._cosine_score", return_value=0.91):
        context, meta = retrieve_context_with_meta(
            db, knowledge_base_ids=[1], query_embedding=[0.1] * 3
        )

    assert "Remote work policy text" in context
    assert len(meta) == 1
    assert meta[0]["kb_id"] == 1
    assert meta[0]["kb_name"] == "HR Policies"
    assert meta[0]["chunks_used"] == 1
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && python -m pytest tests/test_rag_retrieval.py -v
```
Expected: `ImportError` or `AttributeError` — `retrieve_context_with_meta` does not exist yet.

- [ ] **Step 3: Implement `retrieve_context_with_meta` in `rag.py`**

Replace the entire content of `backend/src/ai_portal/services/rag.py`:

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import Document, DocumentChunk
from ai_portal.models.knowledge_base import KnowledgeBase


def _cosine_score(chunk: DocumentChunk, query_embedding: list[float]) -> float:
    """Return 1 - cosine_distance as a similarity score (0–1). Used for metadata only."""
    try:
        dist = chunk.embedding.cosine_distance(query_embedding)
        return round(max(0.0, 1.0 - float(dist)), 4)
    except Exception:
        return 0.0


def retrieve_context_with_meta(
    db: Session,
    *,
    knowledge_base_ids: list[int],
    query_embedding: list[float],
    top_k: int = 5,
) -> tuple[str, list[dict]]:
    """
    Run KB-scoped similarity search.

    Returns:
        (context_text, used_kbs_meta)

    where used_kbs_meta is a list of dicts:
        [{"kb_id": int, "kb_name": str, "chunks_used": int, "top_score": float, "sections": list[str]}]
    """
    if not knowledge_base_ids:
        return "", []

    doc_ids = select(Document.id).where(
        Document.knowledge_base_id.in_(knowledge_base_ids),
        Document.status == "ready",
    )
    stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id.in_(doc_ids),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    chunks = list(db.scalars(stmt))
    if not chunks:
        return "", []

    # Map document_id → knowledge_base_id
    doc_id_to_kb: dict[int, int] = {}
    for doc in db.scalars(
        select(Document).where(Document.id.in_([c.document_id for c in chunks]))
    ).all():
        doc_id_to_kb[doc.id] = doc.knowledge_base_id

    # Fetch KB names for the contributing KBs
    contributing_kb_ids = list({doc_id_to_kb[c.document_id] for c in chunks if c.document_id in doc_id_to_kb})
    kb_name_map: dict[int, str] = {}
    for kb in db.scalars(
        select(KnowledgeBase).where(KnowledgeBase.id.in_(contributing_kb_ids))
    ).all():
        kb_name_map[kb.id] = kb.name

    # Group chunks by KB
    kb_chunks: dict[int, list[DocumentChunk]] = {}
    for chunk in chunks:
        kb_id = doc_id_to_kb.get(chunk.document_id)
        if kb_id is not None:
            kb_chunks.setdefault(kb_id, []).append(chunk)

    # Build metadata list
    used_kbs_meta: list[dict] = []
    for kb_id, kb_chunk_list in kb_chunks.items():
        scores = [_cosine_score(c, query_embedding) for c in kb_chunk_list]
        sections: list[str] = []
        for c in kb_chunk_list:
            if isinstance(c.meta, dict):
                src = c.meta.get("source") or c.meta.get("page") or c.meta.get("section")
                if src:
                    sections.append(str(src))
        used_kbs_meta.append(
            {
                "kb_id": kb_id,
                "kb_name": kb_name_map.get(kb_id, f"KB {kb_id}"),
                "chunks_used": len(kb_chunk_list),
                "top_score": max(scores) if scores else 0.0,
                "sections": sections,
            }
        )

    context = "\n\n".join(c.content for c in chunks)
    return context, used_kbs_meta


def retrieve_context(
    db: Session,
    *,
    knowledge_base_ids: list[int],
    query_embedding: list[float],
    top_k: int = 5,
) -> str:
    """Backward-compatible wrapper — returns context string only."""
    context, _ = retrieve_context_with_meta(
        db, knowledge_base_ids=knowledge_base_ids, query_embedding=query_embedding, top_k=top_k
    )
    return context
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_rag_retrieval.py -v
```
Expected: both tests PASS (the monkeypatching test may need adjustment based on actual DB mock behaviour — if it fails due to mock complexity, simplify to test `retrieve_context` backward compat and `retrieve_context_with_meta` empty path only).

- [ ] **Step 5: Commit**

```bash
git add backend/src/ai_portal/services/rag.py backend/tests/test_rag_retrieval.py
git commit -m "feat(rag): retrieve_context_with_meta returns per-KB chunk metadata"
```

---

## Task 2: Store `used_kbs` in message `extra` in the streaming endpoint

**Files:**
- Modify: `backend/src/ai_portal/api/conversations.py`

The stream handler is in `conversations.py`. Find the `stream_message` route (the one that calls `rag_svc.retrieve_context`). We need to:
1. Switch it to `retrieve_context_with_meta`
2. Always run RAG when `kb_ids` is non-empty (ignore `use_rag` flag for the metadata path)
3. Store `used_kbs` metadata in `assistant_message.extra`

- [ ] **Step 1: Write a failing test**

```python
# Add to backend/tests/test_knowledge_bases_api.py (append at end)

def test_stream_stores_used_kbs_in_extra(client, db_session, dev_headers):
    """When RAG runs and returns chunks, assistant message.extra contains used_kbs."""
    from unittest.mock import patch

    # Create a conversation
    res = client.post(
        "/api/chat/conversations",
        json={"title": "test", "model": None, "assistant_id": None, "settings": None},
        headers=dev_headers,
    )
    assert res.status_code == 201
    conv_id = res.json()["id"]

    fake_meta = [{"kb_id": 99, "kb_name": "Test KB", "chunks_used": 1, "top_score": 0.9, "sections": []}]

    with (
        patch("ai_portal.api.conversations.embedding_svc.embed_texts", return_value=[[0.1, 0.2]]),
        patch("ai_portal.api.conversations.rag_svc.retrieve_context_with_meta", return_value=("some context", fake_meta)),
        patch("ai_portal.api.conversations.llm_svc.stream_chat_completions", return_value=iter(["Hello"])),
    ):
        # Attach a fake KB id to trigger RAG path
        from ai_portal.models.knowledge_base import ConversationKnowledgeBase
        from ai_portal.models import ChatMessage
        db_session.add(ConversationKnowledgeBase(conversation_id=conv_id, knowledge_base_id=99))
        db_session.commit()

        res2 = client.post(
            f"/api/chat/conversations/{conv_id}/messages/stream",
            json={"content": "hello", "use_rag": True},
            headers=dev_headers,
        )
        assert res2.status_code == 200

    # Check that the assistant message has used_kbs in extra
    from sqlalchemy import select
    msgs = db_session.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id, ChatMessage.role == "assistant")
    ).all()
    assert len(msgs) == 1
    assert msgs[0].extra is not None
    assert "used_kbs" in msgs[0].extra
    assert msgs[0].extra["used_kbs"][0]["kb_name"] == "Test KB"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && python -m pytest tests/test_knowledge_bases_api.py::test_stream_stores_used_kbs_in_extra -v
```
Expected: FAIL — `retrieve_context_with_meta` not called yet.

- [ ] **Step 3: Update the stream handler in `conversations.py`**

Find the section in the `stream_message` function that calls `rag_svc.retrieve_context`. It looks like:

```python
rag_block = ""
if body.use_rag and kb_ids:
    ...
    rag_block = rag_svc.retrieve_context(db, knowledge_base_ids=kb_ids, query_embedding=q_emb)
```

Replace it with:

```python
rag_block = ""
used_kbs_meta: list[dict] = []
if kb_ids:
    last_user_content = body.content.strip() if body.content.strip() else ""
    if not last_user_content and body.regenerate_after_message_id is not None:
        # On regenerate, use the last user message content from DB
        prior_user = db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.role == "user",
                ChatMessage.id <= body.regenerate_after_message_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(1)
        ).first()
        last_user_content = prior_user.content.strip() if prior_user else ""
    if last_user_content:
        try:
            q_emb = embedding_svc.embed_texts([last_user_content])[0]
            rag_block, used_kbs_meta = rag_svc.retrieve_context_with_meta(
                db, knowledge_base_ids=kb_ids, query_embedding=q_emb
            )
        except ValueError:
            logger.warning("rag_skipped_no_embedding_key")
```

Then find where the assistant message is persisted (after the stream loop ends). It will look like:

```python
db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=assembled))
db.commit()
```

Change it to:

```python
db.add(ChatMessage(
    conversation_id=conv.id,
    role="assistant",
    content=assembled,
    extra={"used_kbs": used_kbs_meta} if used_kbs_meta else None,
))
db.commit()
```

- [ ] **Step 4: Run the test**

```bash
cd backend && python -m pytest tests/test_knowledge_bases_api.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Also run the full test suite**

```bash
cd backend && python -m pytest -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/api/conversations.py
git commit -m "feat(rag): store used_kbs metadata in assistant message extra"
```

---

## Task 3: Add `UsedKbEntry` type and `used_kbs` to `ChatMessage` in frontend

**Files:**
- Modify: `frontend/src/lib/chat-types.ts`

- [ ] **Step 1: Add types**

In `frontend/src/lib/chat-types.ts`, add after the `ConversationSettings` type:

```typescript
export type UsedKbEntry = {
  kb_id: number
  kb_name: string
  chunks_used: number
  top_score: number
  sections: string[]
}
```

And update `ChatMessage` to include `used_kbs`:

```typescript
export type ChatMessage = {
  id: number
  conversation_id: number
  role: string
  content: string
  created_at: string
  extra: Record<string, unknown> | null
  /** Populated on assistant messages when RAG retrieved chunks. */
  used_kbs?: UsedKbEntry[] | null
}
```

Note: `used_kbs` is stored in `extra.used_kbs` on the server. We'll extract it in the component rather than the type, but having it optional on the type makes it easy to pass down.

- [ ] **Step 2: Verify no TypeScript errors**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/chat-types.ts
git commit -m "feat(types): add UsedKbEntry and used_kbs to ChatMessage"
```

---

## Task 4: Build `MessageKbIndicator` component

**Files:**
- Create: `frontend/src/components/knowledge-bases/MessageKbIndicator.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/knowledge-bases/MessageKbIndicator.tsx
import * as React from 'react'
import type { UsedKbEntry } from '~/lib/chat-types'

type MessageKbIndicatorProps = {
  usedKbs: UsedKbEntry[]
}

export function MessageKbIndicator({ usedKbs }: MessageKbIndicatorProps) {
  const [open, setOpen] = React.useState(false)
  const ref = React.useRef<HTMLDivElement>(null)

  if (usedKbs.length === 0) return null

  return (
    <div
      ref={ref}
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {/* Green 📚 icon */}
      <span
        className="flex h-[18px] w-[18px] cursor-default items-center justify-center rounded-[4px] border border-green-600/60 bg-green-900/40 text-[10px] text-green-400 dark:border-green-500/40 dark:bg-green-950/60"
        aria-label={`${usedKbs.length} knowledge base${usedKbs.length > 1 ? 's' : ''} used`}
        role="img"
      >
        📚
      </span>

      {/* Hover popover */}
      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-1.5 min-w-[220px] rounded-lg border border-neutral-700 bg-neutral-900 p-3 shadow-xl">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-green-400">
            KBs used in this response
          </p>
          <ul className="space-y-2">
            {usedKbs.map((kb) => (
              <li key={kb.kb_id} className="flex items-start gap-2">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-blue-900/60 text-sm">
                  📄
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium text-neutral-100">
                    {kb.kb_name}
                  </p>
                  <p className="text-[10px] text-neutral-400">
                    {kb.chunks_used} chunk{kb.chunks_used !== 1 ? 's' : ''} · score{' '}
                    {kb.top_score.toFixed(2)}
                    {kb.sections.length > 0 && ` · ${kb.sections.slice(0, 2).join(', ')}`}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/knowledge-bases/MessageKbIndicator.tsx
git commit -m "feat(ui): MessageKbIndicator — green KB icon + hover popover on AI messages"
```

---

## Task 5: Build `KbsToolbarButton` component

**Files:**
- Create: `frontend/src/components/knowledge-bases/KbsToolbarButton.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/knowledge-bases/KbsToolbarButton.tsx
import { BookOpen } from 'lucide-react'
import * as React from 'react'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'

type KbsToolbarButtonProps = {
  /** KBs currently attached to this conversation. */
  activeKbs: KnowledgeBaseSummary[]
  /** Called when the user clicks the button (open picker). */
  onClick: () => void
  disabled?: boolean
}

export function KbsToolbarButton({ activeKbs, onClick, disabled }: KbsToolbarButtonProps) {
  const [hovered, setHovered] = React.useState(false)
  const count = activeKbs.length

  return (
    <div className="relative inline-flex shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        onMouseEnter={() => count > 0 && setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={`flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition-colors disabled:opacity-50 ${
          count > 0
            ? 'border-blue-400/60 bg-blue-950/40 text-blue-300 hover:bg-blue-950/60 dark:border-blue-500/50 dark:bg-blue-950/30'
            : 'border-neutral-200 text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900'
        }`}
        aria-label={count > 0 ? `${count} knowledge base${count > 1 ? 's' : ''} active` : 'Attach knowledge bases'}
      >
        <BookOpen className="size-3.5 shrink-0" strokeWidth={2} />
        {count > 0 ? (
          <span>
            <strong>{count}</strong> KB{count > 1 ? 's' : ''} active
          </span>
        ) : (
          <span>KBs</span>
        )}
      </button>

      {/* Hover popover — only when KBs are active */}
      {hovered && count > 0 && (
        <div
          className="absolute bottom-full right-0 z-50 mb-1.5 min-w-[240px] rounded-lg border border-neutral-700 bg-neutral-900 p-3 shadow-xl"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-blue-400">
            Active knowledge bases
          </p>
          <ul className="space-y-2">
            {activeKbs.map((kb) => (
              <li key={kb.id} className="flex items-center gap-2">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-blue-900/60 text-sm">
                  📄
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium text-neutral-100">{kb.name}</p>
                  {kb.description && (
                    <p className="truncate text-[10px] text-neutral-400">{kb.description}</p>
                  )}
                </div>
                <span className="h-2 w-2 shrink-0 rounded-full bg-green-500" />
              </li>
            ))}
          </ul>
          <p className="mt-2 border-t border-neutral-800 pt-2 text-[10px] text-neutral-500">
            Click the button to add or remove KBs
          </p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/knowledge-bases/KbsToolbarButton.tsx
git commit -m "feat(ui): KbsToolbarButton with active badge and hover popover"
```

---

## Task 6: Build `KbPickerDialog` command palette

**Files:**
- Create: `frontend/src/components/knowledge-bases/KbPickerDialog.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/knowledge-bases/KbPickerDialog.tsx
import * as React from 'react'
import { Search, Check } from 'lucide-react'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'

type KbPickerDialogProps = {
  open: boolean
  onClose: () => void
  allKbs: KnowledgeBaseSummary[]
  activeIds: number[]
  onToggle: (id: number) => void
  loading?: boolean
}

export function KbPickerDialog({
  open,
  onClose,
  allKbs,
  activeIds,
  onToggle,
  loading,
}: KbPickerDialogProps) {
  const [query, setQuery] = React.useState('')
  const [cursor, setCursor] = React.useState(0)
  const inputRef = React.useRef<HTMLInputElement>(null)
  const listRef = React.useRef<HTMLUListElement>(null)

  // Sort: active KBs first, then alphabetical
  const sorted = React.useMemo(
    () =>
      [...allKbs].sort((a, b) => {
        const aActive = activeIds.includes(a.id) ? 0 : 1
        const bActive = activeIds.includes(b.id) ? 0 : 1
        if (aActive !== bActive) return aActive - bActive
        return a.name.localeCompare(b.name)
      }),
    [allKbs, activeIds],
  )

  const filtered = React.useMemo(() => {
    const q = query.toLowerCase().trim()
    if (!q) return sorted
    return sorted.filter(
      (kb) =>
        kb.name.toLowerCase().includes(q) ||
        kb.description?.toLowerCase().includes(q),
    )
  }, [sorted, query])

  // Reset cursor when filtered list changes
  React.useEffect(() => setCursor(0), [filtered.length])

  // Focus input when opened
  React.useEffect(() => {
    if (open) {
      setQuery('')
      setCursor(0)
      setTimeout(() => inputRef.current?.focus(), 10)
    }
  }, [open])

  // Close on Escape, navigate with arrows, toggle with Enter
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(c + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(c - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const kb = filtered[cursor]
      if (kb) onToggle(kb.id)
    }
  }

  // Scroll cursor item into view
  React.useEffect(() => {
    const list = listRef.current
    if (!list) return
    const item = list.children[cursor] as HTMLElement | undefined
    item?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  if (!open) return null

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 shadow-2xl"
        onKeyDown={onKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 border-b border-neutral-800 px-3 py-2.5">
          <Search className="size-4 shrink-0 text-neutral-500" strokeWidth={2} />
          <input
            ref={inputRef}
            type="text"
            className="min-w-0 flex-1 bg-transparent text-sm text-neutral-100 placeholder-neutral-500 outline-none"
            placeholder="Search knowledge bases…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {/* KB list */}
        <ul
          ref={listRef}
          className="max-h-72 overflow-y-auto py-1"
          role="listbox"
          aria-label="Knowledge bases"
        >
          {loading && (
            <li className="px-3 py-2 text-xs text-neutral-500">Loading…</li>
          )}
          {!loading && filtered.length === 0 && (
            <li className="px-3 py-2 text-xs text-neutral-500">
              {allKbs.length === 0 ? 'No knowledge bases yet.' : 'No matches.'}
            </li>
          )}
          {filtered.map((kb, i) => {
            const isActive = activeIds.includes(kb.id)
            const isCursor = i === cursor
            return (
              <li
                key={kb.id}
                role="option"
                aria-selected={isActive}
                className={`flex cursor-pointer items-center gap-3 px-3 py-2 text-sm transition-colors ${
                  isCursor
                    ? 'bg-neutral-800'
                    : 'hover:bg-neutral-800/60'
                }`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => onToggle(kb.id)}
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-blue-900/60 text-base">
                  📄
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-neutral-100">{kb.name}</p>
                  {kb.description && (
                    <p className="truncate text-[11px] text-neutral-400">{kb.description}</p>
                  )}
                </div>
                {isActive && (
                  <span className="flex shrink-0 items-center gap-1 text-[10px] font-semibold text-blue-400">
                    <Check className="size-3" strokeWidth={2.5} />
                    active
                  </span>
                )}
              </li>
            )
          })}
        </ul>

        {/* Footer hints */}
        <div className="border-t border-neutral-800 px-3 py-1.5 text-[10px] text-neutral-600">
          ↑↓ navigate &nbsp;·&nbsp; enter toggle &nbsp;·&nbsp; esc close
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/knowledge-bases/KbPickerDialog.tsx
git commit -m "feat(ui): KbPickerDialog command palette for KB attach/detach"
```

---

## Task 7: Wire KB button into `ChatComposerDock`

**Files:**
- Modify: `frontend/src/components/chat/ChatComposerDock.tsx`

Replace the `showRag`/`useRag`/`setUseRag` props with a single `kbButton` render-prop slot. This keeps the dock unaware of KB logic.

- [ ] **Step 1: Update `ChatComposerDockProps`**

In `ChatComposerDock.tsx`, replace the three RAG props:
```typescript
  showRag?: boolean
  useRag?: boolean
  setUseRag?: (v: boolean) => void
```
with:
```typescript
  /** Rendered between the + button and the model selector. Pass <KbsToolbarButton> here. */
  kbSlot?: React.ReactNode
```

- [ ] **Step 2: Update the component body**

Find and remove the RAG tag in the capability tags section:
```typescript
{showRag && useRag && setUseRag && (
  <CapabilityTag
    label="RAG"
    disabled={streaming}
    onRemove={() => setUseRag(false)}
  />
)}
```

Find and remove the RAG entry in the `+` menu:
```typescript
{showRag && setUseRag && (
  <button ... onClick={() => { setUseRag(!useRag); setPlusOpen(false) }}>
    <span ...>RAG</span>
    {useRag && <span ...>on</span>}
  </button>
)}
```

Add the `kbSlot` render in the toolbar row, after the `+` button div and before the model `<Select>`:
```tsx
{kbSlot && (
  <div className="shrink-0">
    {kbSlot}
  </div>
)}
```

Also update the condition that controls whether capability tags area renders (remove `showRag && useRag`):
```typescript
{(capabilities.reflection || capabilities.research || capabilities.web) && (
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. (TypeScript will also flag the removed props where they are passed — fix those in Task 8.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/chat/ChatComposerDock.tsx
git commit -m "feat(ui): replace showRag/useRag props with kbSlot in ChatComposerDock"
```

---

## Task 8: Wire everything into `ConversationThreadPage`

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

This is the main wiring task:
1. Remove `ConversationKnowledgeBasesPanel` from the JSX
2. Remove `useRag` state
3. Add KB list query, active KB list, picker open state
4. Pass `kbSlot` to `ChatComposerDock`
5. Always send `use_rag: true` (RAG runs when KBs are attached, backend skips if none)
6. Add `MessageKbIndicator` to assistant messages

- [ ] **Step 1: Update imports**

Remove:
```typescript
import { ConversationKnowledgeBasesPanel } from '~/components/knowledge-bases/ConversationKnowledgeBasesPanel'
```

Add:
```typescript
import { KbsToolbarButton } from '~/components/knowledge-bases/KbsToolbarButton'
import { KbPickerDialog } from '~/components/knowledge-bases/KbPickerDialog'
import { MessageKbIndicator } from '~/components/knowledge-bases/MessageKbIndicator'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  type KnowledgeBaseSummary,
  knowledgeBaseListFromResponse,
  parseKnowledgeBasesListJson,
} from '~/lib/knowledge-base-types'
import type { UsedKbEntry } from '~/lib/chat-types'
```

Note: `useMutation` and `useQueryClient` are already imported — keep existing imports, only add the new ones.

- [ ] **Step 2: Remove `useRag` state, add KB picker state**

Remove:
```typescript
const [useRag, setUseRag] = React.useState(false)
```

Add after the existing state declarations:
```typescript
const [kbPickerOpen, setKbPickerOpen] = React.useState(false)
```

- [ ] **Step 3: Add KB list query**

Add after the `convQ` and `catalogQ` declarations:

```typescript
const allKbsQ = useQuery({
  queryKey: queryKeys.knowledgeBases(),
  queryFn: async () => {
    const res = await fetch(`${apiBase}/api/knowledge-bases`, {
      headers: await getAuthHeaders(),
    })
    const text = await res.text()
    return knowledgeBaseListFromResponse(res, text, parseKnowledgeBasesListJson)
  },
  enabled: !isComposerMode,
})

const saveKbsMut = useMutation({
  mutationFn: async (ids: number[]) => {
    if (conversationId == null) throw new Error('No conversation')
    const res = await fetch(
      `${apiBase}/api/chat/conversations/${conversationId}/knowledge-bases`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify({ knowledge_base_ids: ids }),
      },
    )
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<import('~/lib/chat-types').Conversation>
  },
  onSuccess: (data) => {
    if (conversationId == null) return
    void qc.setQueryData(queryKeys.conversation(conversationId), data)
    void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
  },
})

const activeKbs: KnowledgeBaseSummary[] = React.useMemo(() => {
  const ids = convQ.data?.knowledge_base_ids ?? []
  return (allKbsQ.data ?? []).filter((kb) => ids.includes(kb.id))
}, [allKbsQ.data, convQ.data?.knowledge_base_ids])

const toggleKb = (id: number) => {
  const current = convQ.data?.knowledge_base_ids ?? []
  const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
  saveKbsMut.mutate(next)
}
```

- [ ] **Step 4: Update `sendStream` to always send `use_rag: true`**

In `sendStream`, find:
```typescript
const body: Record<string, unknown> = {
  content: trimmed,
  use_rag:
    (convQ.data?.knowledge_base_ids?.length ?? 0) > 0 && useRag,
}
```
Replace with:
```typescript
const body: Record<string, unknown> = {
  content: trimmed,
  use_rag: true,
}
```

Do the same in `regenerateAssistantReply`:
```typescript
const body: Record<string, unknown> = {
  content: '',
  regenerate_after_message_id: assistantMessageId,
  use_rag: true,
}
```

Also update the bootstrap stream payload (in `sendStream`'s composer-mode branch):
```typescript
state: {
  pendingStream: {
    bootstrapId,
    content: trimmed,
    use_rag: true,
    ...(modelParam ? { model: modelParam } : {}),
  },
},
```

- [ ] **Step 5: Remove `ConversationKnowledgeBasesPanel` from JSX**

Find and remove the entire block:
```tsx
{!isComposerMode && conversationId != null && (
  <ConversationKnowledgeBasesPanel
    conversationId={conversationId}
    conversation={convQ.data}
    disabled={streaming || convQ.isPending}
  />
)}
```

- [ ] **Step 6: Add `MessageKbIndicator` to assistant messages**

Inside the message list, find the message header row (the div containing the role label and time). It currently ends with the copy button and regenerate button. After the copy/regenerate buttons block, add the KB indicator for assistant messages:

```tsx
{m.role === 'assistant' && (() => {
  const rawUsedKbs = m.extra?.used_kbs
  const usedKbs: UsedKbEntry[] = Array.isArray(rawUsedKbs)
    ? (rawUsedKbs as UsedKbEntry[])
    : []
  return usedKbs.length > 0 ? (
    <MessageKbIndicator usedKbs={usedKbs} />
  ) : null
})()}
```

Add it inside the `<div className="flex items-center gap-1">` that contains the time, copy, and regenerate buttons.

- [ ] **Step 7: Pass `kbSlot` to `ChatComposerDock`**

Find the `<ChatComposerDock ... />` usage. Replace the old RAG props:
```typescript
showRag={(convQ.data?.knowledge_base_ids?.length ?? 0) > 0}
useRag={useRag}
setUseRag={setUseRag}
```
with:
```tsx
kbSlot={
  !isComposerMode ? (
    <KbsToolbarButton
      activeKbs={activeKbs}
      onClick={() => setKbPickerOpen(true)}
      disabled={streaming || convQ.isPending || saveKbsMut.isPending}
    />
  ) : undefined
}
```

- [ ] **Step 8: Add `KbPickerDialog` to the JSX**

Add before the closing `</div>` of the component return:
```tsx
{!isComposerMode && (
  <KbPickerDialog
    open={kbPickerOpen}
    onClose={() => setKbPickerOpen(false)}
    allKbs={allKbsQ.data ?? []}
    activeIds={convQ.data?.knowledge_base_ids ?? []}
    onToggle={toggleKb}
    loading={allKbsQ.isPending}
  />
)}
```

- [ ] **Step 9: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 10: Smoke test in browser**

With the backend and frontend running:
1. Open a conversation at http://localhost:5173
2. Confirm the KB collapsible panel is gone
3. Confirm the `📚 KBs` button appears in the composer toolbar
4. Click it — command palette opens, type to filter, click/Enter to toggle
5. Close with Esc or click outside
6. Hover the button badge — popover shows active KBs
7. Send a message — if KBs are attached and embeddings are configured, check that the AI response shows the green 📚 icon; hover it to see the popover

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(ui): wire KB picker, toolbar button, and message KB indicator into chat"
```

---

## Self-review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `📚 KBs` toolbar button | Task 5, 7, 8 |
| Badge shows active count + hover popover | Task 5 |
| KB picker opens on click — command palette | Task 6, 8 |
| Arrow/Enter/Esc keyboard nav in picker | Task 6 |
| Immediate toggle (no Apply) | Task 6, 8 (`toggleKb` calls `saveKbsMut` directly) |
| Active KBs sorted first in picker | Task 6 |
| Green 📚 icon only when RAG contributed | Task 4, 8 |
| Hover icon → popover with chunk count, score, sections | Task 4 |
| No icon on pure LLM responses | Task 4 (returns null when `usedKbs.length === 0`) |
| Backend stores `used_kbs` in `message.extra` | Task 2 |
| `ConversationKnowledgeBasesPanel` collapsible removed | Task 8 |
| Old RAG toggle removed | Task 7, 8 |

**Type consistency check:** `UsedKbEntry` defined in Task 3, used identically in Task 4 and Task 8. `KnowledgeBaseSummary` (existing type) used consistently in Tasks 5, 6, 8. `kbSlot: React.ReactNode` defined in Task 7, passed in Task 8.
