"""POST /v1/moderations — OpenAI-compatible content moderation.

Wire (request)::

    {"input": "..." | ["...", "..."], "model": "omni-moderation-latest"}

Response::

    {"id": "...", "model": "...",
     "results": [
        {"flagged": bool, "categories": {...bool}, "category_scores": {...float}}
     ]}

Backend selection (which :class:`Moderator` implementation is used) is
policy-driven per org: ``settings.moderation_provider in {openai, anthropic,
llamaguard}``. Tests override :func:`get_moderator` to inject a stub.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_portal.control_plane.deps import require_actor
from ai_portal.core.config import get_settings
from ai_portal.gateway.moderations import (
    CATEGORIES,
    ModerationResult,
    Moderator,
)
from ai_portal.rbac.service import Actor

router = APIRouter(tags=["gateway-moderations"])


# ── schemas ──────────────────────────────────────────────────────────────


class ModerationRequest(BaseModel):
    input: str | list[str] = Field(
        description="One string or a non-empty list of strings"
    )
    model: str | None = None


class ResultOut(BaseModel):
    flagged: bool
    categories: dict[str, bool]
    category_scores: dict[str, float]


class ModerationResponse(BaseModel):
    id: str
    model: str
    results: list[ResultOut]


# ── moderator DI ─────────────────────────────────────────────────────────


def get_moderator() -> Moderator:
    """Pick a moderator backend based on org / global settings.

    Priority follows ``settings.moderation_provider`` if set, otherwise:

    - OpenAI key present     → OpenAIModerator
    - Anthropic key present  → AnthropicCategoriesModerator (with classifier
      that goes through the gateway — not wired here yet)
    - LlamaGuard URL present → LlamaGuardModerator
    - otherwise → 503
    """
    s = get_settings()
    pref = (getattr(s, "moderation_provider", "") or "").strip().lower()

    def _openai():
        from ai_portal.gateway.moderations.providers.openai_moderation import (
            OpenAIModerator,
        )

        return OpenAIModerator(api_key=s.openai_api_key)

    def _llamaguard():
        from ai_portal.gateway.moderations.providers.llamaguard import (
            LlamaGuardModerator,
        )

        return LlamaGuardModerator(
            base_url=getattr(s, "llamaguard_url", "") or "",
            api_key=getattr(s, "llamaguard_api_key", None) or None,
        )

    if pref == "openai" and getattr(s, "openai_api_key", "").strip():
        return _openai()
    if pref == "llamaguard" and getattr(s, "llamaguard_url", "").strip():
        return _llamaguard()
    if not pref:
        if getattr(s, "openai_api_key", "").strip():
            return _openai()
        if getattr(s, "llamaguard_url", "").strip():
            return _llamaguard()
    raise HTTPException(
        status_code=503,
        detail="no moderation provider configured (set MODERATION_PROVIDER + matching credentials)",
    )


# ── route ────────────────────────────────────────────────────────────────


def _to_out(r: ModerationResult) -> ResultOut:
    return ResultOut(
        flagged=r.flagged,
        # Ensure every category present even if provider dropped some.
        categories={c: bool(r.categories.get(c, False)) for c in CATEGORIES},
        category_scores={
            c: float(r.category_scores.get(c, 0.0)) for c in CATEGORIES
        },
    )


@router.post("/v1/moderations", response_model=ModerationResponse)
async def moderations(
    body: ModerationRequest,
    actor: Annotated[Actor, Depends(require_actor)],
    moderator: Annotated[Moderator, Depends(get_moderator)],
) -> ModerationResponse:
    """OpenAI-compatible moderation surface."""
    inputs: list[str]
    if isinstance(body.input, str):
        inputs = [body.input]
    else:
        inputs = list(body.input)
    if not inputs:
        raise HTTPException(status_code=422, detail="input must be non-empty")
    results = await moderator.moderate(inputs, model=body.model)
    return ModerationResponse(
        id=f"modr_{uuid.uuid4().hex[:24]}",
        model=body.model or moderator.name,
        results=[_to_out(r) for r in results],
    )


__all__ = [
    "router",
    "get_moderator",
    "ModerationRequest",
    "ModerationResponse",
]
