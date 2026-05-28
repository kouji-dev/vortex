"""strict_eu policy — GDPR Article 9 special-category gate.

Blocks extraction of memories that mention any of the GDPR Art. 9 special
categories:

- racial/ethnic origin
- political opinions
- religious or philosophical beliefs
- trade-union membership
- genetic data
- biometric data
- health
- sex life / sexual orientation

Detection is regex-based so the policy stays self-contained and does not
depend on Presidio / external services. Production deployments may layer
the Gateway guardrails pipeline on top for additional PII detection.
"""
from __future__ import annotations

import re

from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.recallers.protocol import RecallScope

from .registry import register


_CATEGORY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "racial_ethnic_origin": [
        re.compile(r"\b(race|racial|ethnic(?:ity)?|nationality)\b", re.IGNORECASE),
    ],
    "political_opinions": [
        re.compile(
            r"\b(political|democrat|republican|labour|conservative|socialist|libertarian|"
            r"green party|right[- ]wing|left[- ]wing|vote[ds]?)\b",
            re.IGNORECASE,
        ),
    ],
    "religious_or_philosophical_beliefs": [
        re.compile(
            r"\b(religion|religious|faith|christian|muslim|jewish|hindu|buddhist|atheis[mt]|"
            r"agnostic|spiritual)\b",
            re.IGNORECASE,
        ),
    ],
    "trade_union_membership": [
        re.compile(r"\b(trade[- ]union|labour union|union member(ship)?)\b", re.IGNORECASE),
    ],
    "genetic": [
        re.compile(r"\b(genetic|gene(s)?|DNA|chromosom\w*)\b", re.IGNORECASE),
    ],
    "biometric": [
        re.compile(
            r"\b(biometric|fingerprint|face[- ]?print|retina[l]?|iris scan|voiceprint)\b",
            re.IGNORECASE,
        ),
    ],
    "health": [
        re.compile(
            r"\b(health|diagnos(ed|is)|illness|disease|cancer|diabetes|HIV|AIDS|depression|"
            r"anxiety|mental health|medication|prescription|hospital(i[sz]ed)?)\b",
            re.IGNORECASE,
        ),
    ],
    "sex_life_or_sexual_orientation": [
        re.compile(
            r"\b(sexual orientation|sex life|gay|lesbian|bisexual|asexual|queer|heterosexual|"
            r"homosexual|LGBTQ\+?|transgender)\b",
            re.IGNORECASE,
        ),
    ],
}


class StrictEuPolicy:
    name = "strict_eu"

    async def should_extract(self, turn: Turn, scope: ExtractScope) -> bool:
        return not bool(await self.sensitive_category_match(turn.content))

    async def should_recall(self, query: str, scope: RecallScope) -> bool:
        return not bool(await self.sensitive_category_match(query))

    async def sensitive_category_match(self, text: str) -> list[str]:
        if not text:
            return []
        hits: list[str] = []
        for cat, pats in _CATEGORY_PATTERNS.items():
            for pat in pats:
                if pat.search(text):
                    hits.append(cat)
                    break
        return hits


register(StrictEuPolicy())
