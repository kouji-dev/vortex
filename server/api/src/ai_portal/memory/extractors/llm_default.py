"""llm_default extractor — one caveman-prompt LLM call → JSON memories.

Calls the gateway facade once with the full turn slice. Output JSON shape:

    {"memories": [{"type", "text", "confidence", "source_turn_ids", "tags"}]}

Tests monkeypatch ``gw_complete`` to a stub. The actor used for the call
falls back to a synthetic service actor derived from the scope; production
wiring may inject a real Actor by setting ``ACTOR_FACTORY``.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

from ai_portal.gateway import (
    Actor,
    LLMRequest,
    Message,
    TextBlock,
    complete as gw_complete,
)

from .protocol import Candidate, ExtractOpts, ExtractScope, Turn
from .registry import register

logger = logging.getLogger(__name__)


SYS = (
    "Extract memories from conversation. Output JSON only.\n"
    "- One memory per durable fact, preference, entity, episode, procedure.\n"
    "- Skip greetings, small talk, ephemeral context.\n"
    "- Skip sensitive categories listed in BLOCK.\n"
    "- type in {fact, preference, entity, relation, episode, procedure}\n"
    "- confidence in [0,1]\n"
    "- text: third person, atomic, <240 chars.\n"
    'Return: {"memories": [{"type", "text", "confidence", "source_turn_ids": [...], "tags": [...]}]}'
)


def _default_actor(scope: ExtractScope) -> Actor:
    try:
        org_uuid = uuid.UUID(scope.org_id)
    except Exception:
        org_uuid = uuid.uuid4()
    user_id: int | None
    try:
        user_id = int(scope.actor_user_id)
    except Exception:
        user_id = None
    return Actor(org_id=org_uuid, user_id=user_id, kind="service")


# Production code may override this to plumb a richer Actor / API-key id.
ACTOR_FACTORY: Callable[[ExtractScope], Actor] = _default_actor


def _build_user_message(turns: list[Turn], opts: ExtractOpts) -> str:
    block = ",".join(opts.block_sensitive_categories) or "none"
    body = "\n".join(f"[{t.turn_id}] {t.role}: {t.content}" for t in turns)
    return f"BLOCK: {block}\n\nTURNS:\n{body}"


def _coerce_text(res: Any) -> str:
    content = getattr(res, "content", None)
    if content is None:
        return ""
    parts: list[str] = []
    for b in content:
        # accept canonical TextBlock instances OR dict / namespace fakes.
        text = getattr(b, "text", None)
        if text is None and isinstance(b, dict):
            if b.get("type") == "text":
                text = b.get("text")
        if text:
            parts.append(str(text))
    return "".join(parts)


def _parse(text: str, opts: ExtractOpts) -> list[Candidate]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # tolerate model preludes by grabbing the first {...} blob
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    out: list[Candidate] = []
    for item in parsed.get("memories", []) or []:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        body = (item.get("text") or "").strip()
        conf = float(item.get("confidence", 0.0) or 0.0)
        if typ not in opts.allowed_types or not body:
            continue
        if conf < opts.confidence_floor:
            continue
        out.append(
            Candidate(
                type=typ,
                text=body[:240],
                confidence=conf,
                source_turn_ids=list(item.get("source_turn_ids") or []),
                tags=list(item.get("tags") or []),
            )
        )
        if len(out) >= opts.max_candidates:
            break
    return out


class LlmDefaultExtractor:
    name = "llm_default"

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts,
    ) -> list[Candidate]:
        if not turns:
            return []
        req = LLMRequest(
            model=opts.model,
            messages=[
                Message(role="system", content=[TextBlock(text=SYS)]),
                Message(
                    role="user",
                    content=[TextBlock(text=_build_user_message(turns, opts))],
                ),
            ],
            temperature=0.0,
            max_tokens=1024,
            metadata={"module": "memory", "phase": "extract"},
        )
        actor = ACTOR_FACTORY(scope)
        try:
            res = await gw_complete(req, actor)
        except Exception:
            logger.exception("memory.llm_default.gw_complete_failed")
            return []
        text = _coerce_text(res)
        if not text:
            return []
        return _parse(text, opts)


register(LlmDefaultExtractor())
