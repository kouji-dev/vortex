"""rule_based extractor — cheap regex pre-filter.

Catches a handful of high-signal phrasings ("I prefer X", "I work at X",
"my name is X", "remember that X"). Used as a fast pre-pass before the
LLM extractor.
"""
from __future__ import annotations

import re

from .protocol import Candidate, ExtractOpts, ExtractScope, Turn
from .registry import register


_RULES: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bI\s+prefer\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "preference", 0.8),
    (re.compile(r"\bI\s+like\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "preference", 0.7),
    (re.compile(r"\bremember\s+that\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "fact", 0.9),
    (re.compile(r"\bmy\s+name\s+is\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "entity", 0.95),
    (re.compile(r"\bI\s+work\s+at\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "entity", 0.85),
    (re.compile(r"\bmy\s+repo\s+is\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "entity", 0.85),
    (re.compile(r"\bI\s+always\s+(.+?)(?:[.!?]|$)", re.IGNORECASE), "procedure", 0.7),
]


def _atomic(text: str) -> str:
    return text.strip().rstrip(",;:").strip()[:240]


class RuleBasedExtractor:
    name = "rule_based"

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts,
    ) -> list[Candidate]:
        out: list[Candidate] = []
        for t in turns:
            if t.role != "user":
                continue
            for pat, typ, conf in _RULES:
                if typ not in opts.allowed_types:
                    continue
                for m in pat.finditer(t.content):
                    body = _atomic(m.group(1))
                    if not body:
                        continue
                    if conf < opts.confidence_floor:
                        continue
                    out.append(
                        Candidate(
                            type=typ,
                            text=body,
                            confidence=conf,
                            source_turn_ids=[t.turn_id],
                            tags=["rule_based"],
                        )
                    )
                    if len(out) >= opts.max_candidates:
                        return out
        return out


register(RuleBasedExtractor())
