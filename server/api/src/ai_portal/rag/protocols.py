# src/ai_portal/rag/protocols.py
from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def embeddings_missing_key_message(self) -> str: ...
