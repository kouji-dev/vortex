from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import ThreadItem


class IllegalTransition(RuntimeError):
    pass


@dataclass(slots=True)
class ItemWriter:
    session: Session
    thread_id: int
    org_id: uuid.UUID

    @property
    def db(self) -> Session:
        return self.session

    def insert_user_message(self, *, turn_id: uuid.UUID, text: str, attachments: list[dict]) -> ThreadItem:
        return self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.user_message, role=ItemRole.user,
            data={"text": text, "attachments": attachments},
        )

    def insert_memory_pill(self, *, turn_id: uuid.UUID, count: int) -> ThreadItem:
        return self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.memory_pill, role=ItemRole.system,
            data={"count": count},
        )

    def insert_citation(self, *, turn_id: uuid.UUID, url: str, title: str | None,
                        snippet: str | None, parent_item_id: int | None) -> ThreadItem:
        return self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.citation, role=ItemRole.system,
            data={"url": url, "title": title, "snippet": snippet},
            parent_item_id=parent_item_id,
        )

    def insert_error(self, *, turn_id: uuid.UUID, code: str, message: str) -> ThreadItem:
        return self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.error, role=ItemRole.system,
            data={"code": code, "message": message},
        )

    def insert_turn_end(self, *, turn_id: uuid.UUID, reason: str) -> ThreadItem:
        return self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.turn_end, role=ItemRole.system,
            data={"reason": reason},
        )

    def start_llm_call(self, *, turn_id: uuid.UUID, model: str, iteration_index: int) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.llm_call, role=ItemRole.assistant, status=ItemStatus.streaming,
            model=model, started_at=_now(),
            data={"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0,
                  "cache_creation_input_tokens": 0, "reasoning_tokens": 0,
                  "iteration_index": iteration_index},
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def start_text(self, *, turn_id: uuid.UUID) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.streaming,
            started_at=_now(), data={"text": ""},
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def start_thinking(self, *, turn_id: uuid.UUID) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.thinking, role=ItemRole.assistant, status=ItemStatus.streaming,
            started_at=_now(), data={"text": ""},
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def start_tool_call(self, *, turn_id: uuid.UUID, tool_name: str,
                        provider: str | None, params: dict) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.tool_call, role=ItemRole.assistant, status=ItemStatus.streaming,
            provider=provider, started_at=_now(),
            data={"tool_name": tool_name, "params": params},
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def start_server_tool(self, *, turn_id: uuid.UUID, tool_name: str,
                          provider: str, input_payload: dict) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.server_tool_use, role=ItemRole.assistant, status=ItemStatus.streaming,
            provider=provider, started_at=_now(),
            data={"tool_name": tool_name, "input": input_payload},
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def start_kb_search(self, *, turn_id: uuid.UUID, query: str,
                        kb_ids: list[int]) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.kb_search, role=ItemRole.assistant, status=ItemStatus.streaming,
            provider="kb_search", started_at=_now(),
            data={
                "tool_name": "search_knowledge_base",
                "query": query,
                "kb_ids": list(kb_ids),
                "chunks": [],
            },
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def finish_kb_search(self, *, item_id: int, chunks: list[dict],
                         result_snippet: str | None, error: str | None,
                         latency_ms: int | None) -> ThreadItem:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        data = dict(item.data or {})
        data["chunks"] = chunks
        if result_snippet is not None:
            data["result_snippet"] = result_snippet
        if error is not None:
            data["error"] = error
        item.data = data
        item.latency_ms = latency_ms
        item.cost_usd = Decimal("0")
        item.cost_estimated = True
        item.status = ItemStatus.error if error else ItemStatus.done
        item.finished_at = _now()
        self.session.flush()
        return item

    def append_text_delta(self, item_id: int, delta: str) -> None:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        data = dict(item.data or {})
        data["text"] = (data.get("text") or "") + delta
        item.data = data
        self.session.flush()

    def finalize_text(self, item_id: int) -> ThreadItem:
        return self._finish(item_id, status=ItemStatus.done)

    def finalize_thinking(self, item_id: int) -> ThreadItem:
        return self._finish(item_id, status=ItemStatus.done)

    def finish_llm_call(self, *, item_id: int,
                        input_tokens: int, output_tokens: int,
                        cached_input_tokens: int, cache_creation_input_tokens: int, reasoning_tokens: int,
                        cost_usd: Decimal, cost_estimated: bool) -> ThreadItem:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.data = {
            **(item.data or {}),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "reasoning_tokens": reasoning_tokens,
        }
        item.cost_usd = cost_usd
        item.cost_estimated = cost_estimated
        item.status = ItemStatus.done
        item.finished_at = _now()
        if item.started_at:
            item.latency_ms = int((item.finished_at - item.started_at).total_seconds() * 1000)
        self.session.flush()
        return item

    def fail_llm_call(self, *, item_id: int, error: str) -> ThreadItem:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.status = ItemStatus.error
        item.data = {**(item.data or {}), "error": error}
        item.finished_at = _now()
        self.session.flush()
        return item

    def finish_tool_call(self, *, item_id: int, result_snippet: str | None, error: str | None,
                         cost_usd: Decimal, cost_estimated: bool, latency_ms: int | None) -> ThreadItem:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        data = dict(item.data or {})
        if result_snippet is not None:
            data["result_snippet"] = result_snippet
        if error is not None:
            data["error"] = error
        item.data = data
        item.cost_usd = cost_usd
        item.cost_estimated = cost_estimated
        item.latency_ms = latency_ms
        item.status = ItemStatus.error if error else ItemStatus.done
        item.finished_at = _now()
        self.session.flush()
        return item

    def finish_server_tool(self, *, item_id: int, cost_usd: Decimal, cost_estimated: bool) -> ThreadItem:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.cost_usd = cost_usd
        item.cost_estimated = cost_estimated
        item.status = ItemStatus.done
        item.finished_at = _now()
        self.session.flush()
        return item

    def cancel_turn_items(self, *, turn_id: uuid.UUID, partial_cost: Decimal | None = None) -> int:
        stmt = select(ThreadItem).where(
            ThreadItem.thread_id == self.thread_id,
            ThreadItem.turn_id == turn_id,
            ThreadItem.status == ItemStatus.streaming,
        )
        rows = self.session.execute(stmt).scalars().all()
        for r in rows:
            r.status = ItemStatus.cancelled
            r.finished_at = _now()
            if partial_cost is not None and r.kind == ItemKind.llm_call:
                r.cost_usd = partial_cost
                r.cost_estimated = True
        self.session.flush()
        return len(rows)

    def sweep_stale(self, *, older_than_seconds: int) -> int:
        cutoff = _now() - timedelta(seconds=older_than_seconds)
        stmt = select(ThreadItem).where(
            ThreadItem.thread_id == self.thread_id,
            ThreadItem.status == ItemStatus.streaming,
            ThreadItem.started_at < cutoff,
        )
        rows = self.session.execute(stmt).scalars().all()
        for r in rows:
            r.status = ItemStatus.error
            r.data = {**(r.data or {}), "error": "interrupted"}
            r.finished_at = _now()
        self.session.flush()
        return len(rows)

    def _insert_terminal(self, *, turn_id: uuid.UUID, kind: ItemKind, role: ItemRole,
                         data: dict[str, Any], parent_item_id: int | None = None) -> ThreadItem:
        now = _now()
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=kind, role=role, status=ItemStatus.done,
            data=data, parent_item_id=parent_item_id,
            started_at=now, finished_at=now,
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def _finish(self, item_id: int, status: ItemStatus) -> ThreadItem:
        item = self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.status = status
        item.finished_at = _now()
        if item.started_at:
            item.latency_ms = int((item.finished_at - item.started_at).total_seconds() * 1000)
        self.session.flush()
        return item

    def _get_and_require_status(self, item_id: int, allowed: set[ItemStatus]) -> ThreadItem:
        stmt = select(ThreadItem).where(
            ThreadItem.id == item_id,
            ThreadItem.thread_id == self.thread_id,
        )
        item = self.session.execute(stmt).scalar_one_or_none()
        if item is None:
            raise IllegalTransition(f"item {item_id} not found in thread {self.thread_id}")
        if item.status not in allowed:
            raise IllegalTransition(f"item {item_id} in status {item.status}, allowed {allowed}")
        return item


def _now() -> datetime:
    return datetime.now(timezone.utc)
