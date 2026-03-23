"""Default ``catalog_metadata["config"]`` payloads (shared: Alembic backfill + seed).

Keys are **portal catalog slugs** (see ``litellm_catalog_definitions`` / ``CONFIG_BY_SLUG``).
"""

from __future__ import annotations

from typing import Any


def _tokens(default: int, cap: int) -> dict[str, Any]:
    return {"min": 1, "max": cap, "default": default}


def _temp(
    min_v: float = 0.0,
    max_v: float = 2.0,
    default: float = 0.7,
) -> dict[str, Any]:
    return {"min": min_v, "max": max_v, "default": default}


def _temp_claude(
    min_v: float = 0.0,
    max_v: float = 1.0,
    default: float = 1.0,
) -> dict[str, Any]:
    """Anthropic Messages API uses temperature in ``[0, 1]``."""
    return {"min": min_v, "max": max_v, "default": default}


# --- Legacy (Alembic 011 backfill for rows created in migration 010) ---

CONFIG_GPT4O_MINI: dict[str, Any] = {
    "reasoning": {
        "supported": False,
        "efforts_available": [],
        "default_effort": None,
    },
    "sampling": {
        "temperature": _temp(),
        "max_output_tokens": _tokens(4096, 16_384),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

# --- Anthropic Opus (current seed) ---

_CONFIG_ANTHROPIC_OPUS_45: dict[str, Any] = {
    "reasoning": {
        "supported": False,
        "efforts_available": [],
        "default_effort": None,
    },
    "sampling": {
        "temperature": _temp_claude(),
        "max_output_tokens": _tokens(8192, 128_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

_CONFIG_ANTHROPIC_OPUS_46: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["minimal", "low", "medium", "high"],
        "default_effort": "medium",
    },
    "sampling": {
        "temperature": _temp_claude(0.0, 1.0, 1.0),
        "max_output_tokens": _tokens(16_384, 128_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

# Same API model as Opus 4.6; catalog row is entitlement-gated for 1M-context orgs.
_CONFIG_ANTHROPIC_OPUS_46_1M: dict[str, Any] = _CONFIG_ANTHROPIC_OPUS_46

# Haiku 4.5 — lowest API tier; 64k max output per Anthropic models table.
_CONFIG_ANTHROPIC_HAIKU_45: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["minimal", "low", "medium", "high"],
        "default_effort": "low",
    },
    "sampling": {
        "temperature": _temp_claude(0.0, 1.0, 1.0),
        "max_output_tokens": _tokens(8192, 64_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

# Sonnet 4.5 — balanced tier; 64k max output per Anthropic models table.
_CONFIG_ANTHROPIC_SONNET_45: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["minimal", "low", "medium", "high"],
        "default_effort": "medium",
    },
    "sampling": {
        "temperature": _temp_claude(0.0, 1.0, 1.0),
        "max_output_tokens": _tokens(16_384, 64_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

# Sonnet 4.6 — balanced tier; 64k max output per Anthropic models table.
_CONFIG_ANTHROPIC_SONNET_46: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["minimal", "low", "medium", "high"],
        "default_effort": "medium",
    },
    "sampling": {
        "temperature": _temp_claude(0.0, 1.0, 1.0),
        "max_output_tokens": _tokens(16_384, 64_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

# --- OpenAI (current seed) ---

_CONFIG_O3_MINI: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["low", "medium", "high"],
        "default_effort": "medium",
    },
    "sampling": {
        "temperature": None,
        "max_output_tokens": _tokens(8192, 100_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

_CONFIG_GPT_45_PREVIEW: dict[str, Any] = {
    "reasoning": {
        "supported": False,
        "efforts_available": [],
        "default_effort": None,
    },
    "sampling": {
        "temperature": _temp(),
        "max_output_tokens": _tokens(8192, 128_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

_CONFIG_GPT_53_CHAT: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["minimal", "low", "medium", "high"],
        "default_effort": "medium",
    },
    "sampling": {
        "temperature": _temp(),
        "max_output_tokens": _tokens(8192, 128_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

_CONFIG_GPT_54: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["minimal", "low", "medium", "high"],
        "default_effort": "medium",
    },
    "sampling": {
        "temperature": _temp(),
        "max_output_tokens": _tokens(16_384, 128_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

_CONFIG_GPT_CODEX_HEAVY: dict[str, Any] = {
    "reasoning": {
        "supported": True,
        "efforts_available": ["low", "medium", "high"],
        "default_effort": "high",
    },
    "sampling": {
        "temperature": _temp(0.0, 1.0, 0.7),
        "max_output_tokens": _tokens(16_384, 128_000),
    },
    "features": {
        "streaming": True,
        "vision": True,
        "tools": True,
        "json_mode": True,
    },
}

_CONFIG_GPT_CODEX_MED: dict[str, Any] = {
    **_CONFIG_GPT_CODEX_HEAVY,
    "reasoning": {
        "supported": True,
        "efforts_available": ["low", "medium", "high"],
        "default_effort": "medium",
    },
}

_CONFIG_GPT_CODEX_MINI: dict[str, Any] = {
    **_CONFIG_GPT_CODEX_HEAVY,
    "reasoning": {
        "supported": False,
        "efforts_available": [],
        "default_effort": None,
    },
    "sampling": {
        "temperature": _temp(),
        "max_output_tokens": _tokens(8192, 64_000),
    },
}


CONFIG_BY_SLUG: dict[str, dict[str, Any]] = {
    "anthropic-claude-haiku-4-5": _CONFIG_ANTHROPIC_HAIKU_45,
    "anthropic-claude-opus-4-5": _CONFIG_ANTHROPIC_OPUS_45,
    "anthropic-claude-opus-4-6": _CONFIG_ANTHROPIC_OPUS_46,
    "anthropic-claude-opus-4-6-1m": _CONFIG_ANTHROPIC_OPUS_46_1M,
    "anthropic-claude-sonnet-4-5": _CONFIG_ANTHROPIC_SONNET_45,
    "anthropic-claude-sonnet-4-6": _CONFIG_ANTHROPIC_SONNET_46,
    "openai-o3-mini": _CONFIG_O3_MINI,
    "openai-gpt-4-5-preview": _CONFIG_GPT_45_PREVIEW,
    "openai-gpt-5-3-chat-latest": _CONFIG_GPT_53_CHAT,
    "openai-gpt-5-4": _CONFIG_GPT_54,
    "openai-gpt-5-3-codex": _CONFIG_GPT_CODEX_HEAVY,
    "openai-gpt-5-3-codex-fast": _CONFIG_GPT_CODEX_MED,
    "openai-gpt-5-3-codex-low": _CONFIG_GPT_CODEX_MINI,
    "openai-gpt-5-4-codex": _CONFIG_GPT_CODEX_HEAVY,
    "openai-gpt-5-4-codex-fast": _CONFIG_GPT_CODEX_MED,
    "openai-gpt-5-4-codex-low": _CONFIG_GPT_CODEX_MINI,
}

# Alembic 011: merge ``config`` onto existing rows from migration 010.
CATALOG_CONFIG_BACKFILL_BY_SLUG: dict[str, dict[str, Any]] = {
    "gpt-4o-mini": CONFIG_GPT4O_MINI,
}

# Back-compat names (older imports / docs).
OPENAI_CATALOG_CONFIG_BY_SLUG = CONFIG_BY_SLUG
ANTHROPIC_CATALOG_CONFIG_BY_SLUG = CONFIG_BY_SLUG
AZURE_CATALOG_CONFIG_BY_SLUG: dict[str, dict[str, Any]] = {}
