"""Shared OpenAI-compatible API base URL normalization."""

from __future__ import annotations


def normalize_openai_compatible_base(base: str) -> str:
    b = base.strip().rstrip("/")
    if not b.endswith("/v1"):
        b = f"{b}/v1"
    return b
