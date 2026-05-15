"""Memory extraction — one LLM call per finished turn.

Runs as a fire-and-forget task from the orchestrator. Pulls candidate facts
about the user from the just-finished user→assistant exchange and persists
them as ``user_memories`` rows with ``source='auto'``.

Caveman style: only fact-shaped statements about the user, deduped against
the user's existing memory list. No prose, no commentary.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Cap how many auto-memories a single turn can add — keeps the list usable
# even with a chatty model.
_MAX_NEW_PER_TURN = 5
_MAX_FACT_CHARS = 240

_SYSTEM_PROMPT = (
    "Memory extractor.\n"
    "- Input: a single user message + the assistant's reply.\n"
    "- Output: JSON array of strings — facts worth remembering about the user.\n"
    "- Each fact: short imperative ('User prefers X', 'User works at Y'). 3-15 words.\n"
    "- ONLY facts the user volunteered about themselves, their work, their preferences.\n"
    "- Skip generic chitchat, questions, transient context, anything from the assistant.\n"
    "- 0-5 facts. If nothing memorable: return `[]`.\n"
    "- Reply with ONLY the JSON array. No prose. No code fences."
)


def _clean_fact(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > _MAX_FACT_CHARS:
        s = s[: _MAX_FACT_CHARS - 1].rstrip() + "…"
    return s


def _parse_facts(text: str) -> list[str]:
    s = (text or "").strip()
    # Be lenient: strip code fences a chatty model might add.
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # Fallback: split by newlines / bullets.
        data = [line.lstrip("-•* ").strip() for line in s.splitlines() if line.strip()]
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str):
            cleaned = _clean_fact(item)
            if cleaned:
                out.append(cleaned)
    return out[:_MAX_NEW_PER_TURN]


def extract_memories(
    provider: Any,
    model: str,
    user_text: str,
    assistant_text: str,
    existing_facts: list[str],
) -> list[str]:
    """Synchronous LLM call. Returns deduped new facts (empty list on failure)."""
    if not (user_text or "").strip():
        return []
    excerpt_user = user_text.strip()[:2000]
    excerpt_asst = (assistant_text or "").strip()[:2000]
    existing_block = "\n".join(f"- {f}" for f in existing_facts[:50]) or "(none)"
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Existing facts about this user (do not repeat):\n"
                f"{existing_block}\n\n"
                "Latest turn:\n"
                f"USER: {excerpt_user}\n\n"
                f"ASSISTANT: {excerpt_asst}\n\n"
                "Return the JSON array of new facts (0-5)."
            ),
        },
    ]
    try:
        resp = provider.complete(messages, model=model)
        text = resp["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_extractor_provider_failed", extra={"err": str(exc)})
        return []
    facts = _parse_facts(text)
    # Dedupe (case-insensitive) against existing.
    existing_lower = {f.strip().lower() for f in existing_facts}
    return [f for f in facts if f.strip().lower() not in existing_lower]
