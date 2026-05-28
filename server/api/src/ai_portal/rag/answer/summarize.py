"""Multi-turn history compression for RAG answer.

When a conversation grows past ``threshold_turns`` prior turns, compress the
older turns into a single ``summary`` string (kept under ``budget_tokens``)
so the rewrite + answer stages keep recent verbatim context but still know
what came before.

Two-phase split:

- ``older_turns``  → summarized via Gateway facade.
- ``recent_turns`` → passed through verbatim (last ``keep_recent`` turns).

If summarization fails (gateway absent, error), falls back to a heuristic
truncation: last ``budget_tokens // 4`` characters of concatenated older
turns. Never raises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from ai_portal.rag.answer.rewrite import ChatTurn

log = logging.getLogger(__name__)


# Caller-injectable LLM facade. Default uses the gateway.
CompleteFn = Callable[[str, str, str], str]


@dataclass(frozen=True)
class CompressedHistory:
    summary: str            # compressed older turns (may be empty)
    recent: list[ChatTurn]  # last N kept verbatim
    compressed: bool        # True when summarization happened


_DEFAULT_THRESHOLD_TURNS = 6
_DEFAULT_KEEP_RECENT = 4
_DEFAULT_BUDGET_TOKENS = 4_000
# Cheap proxy: ~4 chars per token. Keep an upper char bound for the prompt.
_CHARS_PER_TOKEN = 4


def _default_complete(system: str, user: str, model: str) -> str:
    """Gateway facade; raises when unavailable."""
    from ai_portal.gateway import complete as gw_complete  # type: ignore

    res = gw_complete(model=model, system=system, user=user)
    return getattr(res, "text", str(res))


def _heuristic_summary(older: list[ChatTurn], *, budget_chars: int) -> str:
    """No-LLM fallback: keep the tail of older turns up to ``budget_chars``."""
    if not older:
        return ""
    text = "\n".join(f"{t.role}: {t.text}" for t in older)
    if len(text) <= budget_chars:
        return text
    return "…" + text[-budget_chars:]


def compress_history(
    prior_turns: list[ChatTurn],
    *,
    threshold_turns: int = _DEFAULT_THRESHOLD_TURNS,
    keep_recent: int = _DEFAULT_KEEP_RECENT,
    budget_tokens: int = _DEFAULT_BUDGET_TOKENS,
    model: str = "gpt-4o-mini",
    complete_fn: CompleteFn | None = None,
) -> CompressedHistory:
    """Split + compress ``prior_turns`` once they exceed ``threshold_turns``.

    Idempotent on short histories — short histories pass straight through.
    """
    if not prior_turns or len(prior_turns) <= threshold_turns:
        return CompressedHistory(summary="", recent=list(prior_turns or []), compressed=False)

    older = prior_turns[:-keep_recent] if keep_recent > 0 else list(prior_turns)
    recent = prior_turns[-keep_recent:] if keep_recent > 0 else []

    budget_chars = max(200, budget_tokens * _CHARS_PER_TOKEN)
    older_text = "\n".join(f"{t.role}: {t.text}" for t in older)
    # Truncate the input to the summarizer so we honor the budget on both sides.
    if len(older_text) > budget_chars * 2:
        older_text = older_text[-(budget_chars * 2):]

    system = (
        "Summarize chat history.\n"
        "- Preserve named entities, decisions, open questions.\n"
        "- Drop greetings, filler, retrieved-doc dumps.\n"
        "- Output a single dense paragraph. No headings."
    )
    user = f"History:\n{older_text}\n\nSummary:"

    fn = complete_fn or _default_complete
    summary = ""
    try:
        out = fn(system, user, model)
        if out:
            summary = out.strip()
            # Hard cap on output too.
            if len(summary) > budget_chars:
                summary = summary[:budget_chars].rstrip() + "…"
    except Exception:  # noqa: BLE001
        log.warning("history summarize failed; falling back", exc_info=True)
        summary = _heuristic_summary(older, budget_chars=budget_chars)

    if not summary:
        summary = _heuristic_summary(older, budget_chars=budget_chars)

    return CompressedHistory(summary=summary, recent=recent, compressed=True)


__all__ = ["CompressedHistory", "compress_history"]
