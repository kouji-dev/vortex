from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.item_kinds import ItemKind
from ai_portal.chat.model import ThreadItem


async def build_provider_messages(
    *, session: AsyncSession, thread_id: int, org_id: uuid.UUID,
    system_prompt: str, window_size: int,
) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(ThreadItem)
        .where(ThreadItem.thread_id == thread_id, ThreadItem.org_id == org_id)
        .order_by(ThreadItem.created_at, ThreadItem.id)
    )).scalars().all()

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    seen_turns: list[uuid.UUID] = []
    by_turn: dict[uuid.UUID, list[ThreadItem]] = {}
    for item in rows:
        if item.turn_id not in by_turn:
            seen_turns.append(item.turn_id)
            by_turn[item.turn_id] = []
        by_turn[item.turn_id].append(item)

    for turn in seen_turns:
        for item in by_turn[turn]:
            if item.kind == ItemKind.user_message:
                messages.append({"role": "user", "content": item.data["text"]})
            elif item.kind == ItemKind.assistant_text:
                messages.append({"role": "assistant", "content": item.data.get("text") or ""})
            elif item.kind == ItemKind.tool_call:
                messages.append({
                    "role": "assistant", "content": "",
                    "tool_calls": [{
                        "id": f"call_{item.id}", "type": "function",
                        "function": {
                            "name": item.data["tool_name"],
                            "arguments": json.dumps(item.data.get("params") or {}),
                        },
                    }],
                })
                if item.data.get("result_snippet") is not None:
                    messages.append({
                        "role": "tool", "tool_call_id": f"call_{item.id}",
                        "content": item.data["result_snippet"],
                    })

    head = messages[:1]
    tail = messages[1:]
    if len(tail) > window_size:
        tail = tail[-window_size:]
    return head + tail
