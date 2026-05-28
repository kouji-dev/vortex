"""no_op extractor — always returns an empty candidate list.

Useful as a default when extraction is disabled at the policy level, and
as a baseline for tests.
"""
from __future__ import annotations

from .protocol import Candidate, ExtractOpts, ExtractScope, Turn
from .registry import register


class NoOpExtractor:
    name = "no_op"

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts,
    ) -> list[Candidate]:
        return []


register(NoOpExtractor())
