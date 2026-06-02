"""Infer the agent runtime (CLI) from a model id. Only Claude + Codex models are
usable_in_worker, so the mapping is total over the worker catalog."""
from __future__ import annotations


def infer_runtime(api_model_id: str) -> str:
    mid = api_model_id.lower()
    if mid.startswith("claude-"):
        return "claude"
    if "codex" in mid:
        return "codex"
    raise ValueError(f"no agent runtime for model {api_model_id!r}")
