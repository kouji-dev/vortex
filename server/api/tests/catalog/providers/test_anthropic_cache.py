"""E3: Anthropic-native prompt-cache pass-through.

When :class:`LLMRequest` carries a :class:`CacheHint` (or its messages
contain :class:`TextBlock` with ``cache_control``), the Anthropic native
provider attaches ``cache_control`` to the outgoing Anthropic SDK body so
prompt caching kicks in. No hint → no cache_control → no implicit
discount.
"""

from __future__ import annotations

from ai_portal.catalog.providers.anthropic_native import (
    build_system_blocks_from_request,
)
from ai_portal.gateway.types import (
    CacheHint,
    LLMRequest,
    Message,
    TextBlock,
)


def _req(
    *,
    system: str | None = "You are helpful.",
    cache_hints: list[CacheHint] | None = None,
    system_cache: CacheHint | None = None,
) -> LLMRequest:
    messages: list[Message] = []
    if system:
        messages.append(
            Message(
                role="system",
                content=[TextBlock(text=system, cache_control=system_cache)],
            )
        )
    messages.append(
        Message(role="user", content=[TextBlock(text="hi")])
    )
    return LLMRequest(model="claude-sonnet-4-6", messages=messages, cache_hints=cache_hints)


# ── tests ─────────────────────────────────────────────────────────────────


def test_no_cache_hint_no_cache_control() -> None:
    """No cache_hints → outgoing system block has no cache_control marker."""
    blocks = build_system_blocks_from_request(_req())
    assert isinstance(blocks, list)
    assert blocks[0]["text"] == "You are helpful."
    assert "cache_control" not in blocks[0]


def test_request_level_cache_hint_sets_ephemeral_on_system() -> None:
    """``cache_hints`` at request level → ephemeral cache_control on system."""
    blocks = build_system_blocks_from_request(_req(cache_hints=[CacheHint(ttl="5m")]))
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_per_block_cache_control_sets_ephemeral() -> None:
    """A :class:`TextBlock` with ``cache_control`` propagates to outgoing body."""
    blocks = build_system_blocks_from_request(
        _req(system_cache=CacheHint(ttl="5m"))
    )
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_one_hour_ttl_sets_anthropic_1h_marker() -> None:
    """``ttl="1h"`` cache hint maps to Anthropic's 1h cache tier."""
    blocks = build_system_blocks_from_request(
        _req(cache_hints=[CacheHint(ttl="1h")])
    )
    assert blocks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_empty_system_returns_empty_str() -> None:
    blocks = build_system_blocks_from_request(_req(system=None))
    assert blocks == ""
