"""Moderation provider tests — OpenAI, Anthropic-categories (derived),
LlamaGuard (self-hosted).
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from ai_portal.gateway.moderations import CATEGORIES, ModerationResult


# ── OpenAI moderation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_moderator_parses_openai_shape():
    """OpenAI moderation returns ``{"results": [{...}], "model": "..."}``."""
    from ai_portal.gateway.moderations.providers.openai_moderation import (
        OpenAIModerator,
    )

    payload = {
        "id": "modr_x",
        "model": "omni-moderation-latest",
        "results": [
            {
                "flagged": True,
                "categories": {
                    "sexual": False,
                    "hate": True,
                    "harassment": False,
                    "self-harm": False,
                    "sexual/minors": False,
                    "hate/threatening": False,
                    "violence/graphic": False,
                    "self-harm/intent": False,
                    "self-harm/instructions": False,
                    "harassment/threatening": False,
                    "violence": False,
                },
                "category_scores": {
                    "hate": 0.94,
                },
            }
        ],
    }
    with respx.mock(base_url="https://api.openai.com") as mock:
        route = mock.post("/v1/moderations").mock(
            return_value=Response(200, json=payload)
        )
        m = OpenAIModerator(api_key="sk-xxx")
        out = await m.moderate(["bad text"])
        assert route.called
        assert len(out) == 1
        assert out[0].flagged is True
        assert out[0].categories["hate"] is True
        assert out[0].category_scores["hate"] == 0.94
        # Missing categories filled with defaults.
        for c in CATEGORIES:
            assert c in out[0].categories
            assert c in out[0].category_scores


@pytest.mark.asyncio
async def test_openai_moderator_handles_clean_input():
    from ai_portal.gateway.moderations.providers.openai_moderation import (
        OpenAIModerator,
    )

    clean = {
        "results": [
            {
                "flagged": False,
                "categories": {c: False for c in CATEGORIES},
                "category_scores": {c: 0.01 for c in CATEGORIES},
            }
        ]
    }
    with respx.mock(base_url="https://api.openai.com") as mock:
        mock.post("/v1/moderations").mock(return_value=Response(200, json=clean))
        m = OpenAIModerator(api_key="x")
        out = await m.moderate(["hello world"])
        assert out[0].flagged is False
        assert not any(out[0].categories.values())


# ── Anthropic (derived categories) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_moderator_derives_categories_from_classifier_call():
    """Anthropic has no native moderation API. We derive categories by
    asking Claude to classify the text against the standard category list
    and return JSON. Provider parses that JSON.
    """
    from ai_portal.gateway.moderations.providers.anthropic_categories import (
        AnthropicCategoriesModerator,
    )

    async def fake_classify(text: str) -> dict:
        return {
            "violence": 0.82,
            "hate": 0.1,
            "self-harm": 0.05,
        }

    m = AnthropicCategoriesModerator(
        api_key="anth", classifier=fake_classify, threshold=0.5
    )
    out = await m.moderate(["how to hurt someone"])
    assert isinstance(out[0], ModerationResult)
    assert out[0].flagged is True
    assert out[0].categories["violence"] is True
    assert out[0].categories["hate"] is False
    assert out[0].category_scores["violence"] == 0.82
    # Unspecified categories defaulted to 0 / False.
    for c in CATEGORIES:
        assert c in out[0].categories


@pytest.mark.asyncio
async def test_anthropic_moderator_returns_unflagged_when_all_below_threshold():
    from ai_portal.gateway.moderations.providers.anthropic_categories import (
        AnthropicCategoriesModerator,
    )

    async def low(text: str) -> dict:
        return {"hate": 0.1, "violence": 0.2}

    m = AnthropicCategoriesModerator(api_key="x", classifier=low, threshold=0.5)
    out = await m.moderate(["a"])
    assert out[0].flagged is False


# ── LlamaGuard (self-hosted) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llamaguard_moderator_parses_unsafe_response():
    """LlamaGuard responds with ``unsafe\\nS1,S5`` for unsafe items where
    ``S1..Sn`` are MLCommons category codes.
    """
    from ai_portal.gateway.moderations.providers.llamaguard import (
        LlamaGuardModerator,
    )

    # LlamaGuard surface uses chat-completion-shaped responses. We mock at
    # the HTTP layer (Llama.cpp / vllm openai-compat endpoint).
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "unsafe\nS1,S5",
                }
            }
        ]
    }
    with respx.mock(base_url="http://llamaguard.local") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=Response(200, json=payload)
        )
        m = LlamaGuardModerator(base_url="http://llamaguard.local")
        out = await m.moderate(["dangerous text"])
        assert out[0].flagged is True
        # S1 = Violent Crimes → violence; S5 = Defamation/Harassment.
        assert out[0].categories["violence"] is True
        assert out[0].categories["harassment"] is True


@pytest.mark.asyncio
async def test_llamaguard_moderator_parses_safe_response():
    from ai_portal.gateway.moderations.providers.llamaguard import (
        LlamaGuardModerator,
    )

    payload = {"choices": [{"message": {"role": "assistant", "content": "safe"}}]}
    with respx.mock(base_url="http://lg.local") as mock:
        mock.post("/v1/chat/completions").mock(
            return_value=Response(200, json=payload)
        )
        m = LlamaGuardModerator(base_url="http://lg.local")
        out = await m.moderate(["hello"])
        assert out[0].flagged is False
        assert not any(out[0].categories.values())
