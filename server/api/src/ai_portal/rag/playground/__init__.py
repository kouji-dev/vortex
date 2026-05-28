"""KB chat playground — POST a query, get retrieved chunks + answer.

Sessions are persisted in ``kb_playground_sessions`` so they can be replayed
deterministically (same retrieved chunks captured) and promoted to eval
test cases.
"""
from ai_portal.rag.playground.schemas import (
    PlaygroundRequest,
    PlaygroundResponse,
    PlaygroundSessionOut,
    RetrievedChunk,
)
from ai_portal.rag.playground.service import KbPlaygroundService

__all__ = [
    "KbPlaygroundService",
    "PlaygroundRequest",
    "PlaygroundResponse",
    "PlaygroundSessionOut",
    "RetrievedChunk",
]
