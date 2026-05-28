"""llm_typed extractor — one LLM call per memory type.

Reuses ``LlmDefaultExtractor``'s parsing utilities but issues one call per
type with a tailored caveman prompt. Yields the union of all candidates.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Callable

from ai_portal.gateway import (
    Actor,
    LLMRequest,
    Message,
    TextBlock,
    complete as gw_complete,
)

from . import llm_default
from .protocol import Candidate, ExtractOpts, ExtractScope, Turn
from .registry import register

logger = logging.getLogger(__name__)


_PER_TYPE_PROMPT: dict[str, str] = {
    "fact": (
        "Extract durable atomic FACTS about the user. JSON only.\n"
        '{"memories": [{"type": "fact", "text", "confidence", "source_turn_ids"}]}'
    ),
    "preference": (
        "Extract UI / formatting / tone PREFERENCES of the user. JSON only.\n"
        '{"memories": [{"type": "preference", "text", "confidence", "source_turn_ids"}]}'
    ),
    "entity": (
        "Extract named ENTITIES (people, repos, projects, customers). JSON only.\n"
        '{"memories": [{"type": "entity", "text", "confidence", "source_turn_ids"}]}'
    ),
    "relation": (
        "Extract RELATIONS between two entities. JSON only.\n"
        '{"memories": [{"type": "relation", "text", "confidence", "source_turn_ids"}]}'
    ),
    "episode": (
        "Summarise the interaction as one EPISODE memory with timestamp. JSON only.\n"
        '{"memories": [{"type": "episode", "text", "confidence", "source_turn_ids"}]}'
    ),
    "procedure": (
        "Extract how-the-user-does-X PROCEDURES. JSON only.\n"
        '{"memories": [{"type": "procedure", "text", "confidence", "source_turn_ids"}]}'
    ),
}


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


ACTOR_FACTORY: Callable[[ExtractScope], Actor] = _default_actor


class LlmTypedExtractor:
    name = "llm_typed"

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts,
    ) -> list[Candidate]:
        if not turns:
            return []
        actor = ACTOR_FACTORY(scope)
        types = [t for t in opts.allowed_types if t in _PER_TYPE_PROMPT]
        body = "\n".join(f"[{t.turn_id}] {t.role}: {t.content}" for t in turns)
        block = ",".join(opts.block_sensitive_categories) or "none"
        user_msg = f"BLOCK: {block}\n\nTURNS:\n{body}"

        async def _one(typ: str) -> list[Candidate]:
            req = LLMRequest(
                model=opts.model,
                messages=[
                    Message(role="system", content=[TextBlock(text=_PER_TYPE_PROMPT[typ])]),
                    Message(role="user", content=[TextBlock(text=user_msg)]),
                ],
                temperature=0.0,
                max_tokens=512,
                metadata={"module": "memory", "phase": "extract", "type": typ},
            )
            try:
                res = await gw_complete(req, actor)
            except Exception:
                logger.exception("memory.llm_typed.gw_complete_failed", extra={"type": typ})
                return []
            text = llm_default._coerce_text(res)
            cands = llm_default._parse(text, opts)
            # only keep candidates matching the requested type
            return [c for c in cands if c.type == typ]

        results = await asyncio.gather(*(_one(t) for t in types))
        merged: list[Candidate] = []
        for r in results:
            merged.extend(r)
            if len(merged) >= opts.max_candidates:
                return merged[: opts.max_candidates]
        return merged


register(LlmTypedExtractor())
