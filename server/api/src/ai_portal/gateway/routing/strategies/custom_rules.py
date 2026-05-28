"""Custom-rules strategy — first matching rule wins, else fallback.

Rules shape:

.. code-block:: json

    {
      "rules": [
        {"if": {"model_startswith": "smart"},
         "then": {"provider": "openai", "model_id": "gpt-4o"}},
        {"if": {"contains_text": "code"},
         "then": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"}},
        {"if": {"min_messages": 10},
         "then": {"provider": "gemini", "model_id": "gemini-2.5-flash"}}
      ],
      "fallback": {"provider": "openai", "model_id": "gpt-4o"}
    }

Supported predicates inside ``if``:

- ``model_startswith`` / ``model_equals`` — match request's ``model``.
- ``contains_text`` — substring search across request text content (case-insensitive).
- ``min_messages`` — at least N messages in the request.
- ``has_tools`` — request defines at least one tool.
- ``has_images`` — at least one ``ImageBlock`` in any message.

``then`` follows the same shape as :class:`StaticStrategy.rules` — a
concrete ``(provider, model_id)`` pair that must exist in candidates.
"""

from __future__ import annotations

from typing import Any

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
    RoutingStrategy,
)
from ai_portal.gateway.types import LLMRequest


def _all_text(req: LLMRequest) -> str:
    parts: list[str] = []
    for m in req.messages:
        for block in m.content:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
    return " ".join(parts).lower()


def _has_images(req: LLMRequest) -> bool:
    for m in req.messages:
        for block in m.content:
            if getattr(block, "type", None) == "image":
                return True
    return False


def _matches(pred: dict[str, Any], req: LLMRequest) -> bool:
    if "model_startswith" in pred and not req.model.startswith(
        pred["model_startswith"]
    ):
        return False
    if "model_equals" in pred and req.model != pred["model_equals"]:
        return False
    if "contains_text" in pred:
        needle = str(pred["contains_text"]).lower()
        if needle not in _all_text(req):
            return False
    if "min_messages" in pred and len(req.messages) < int(pred["min_messages"]):
        return False
    if pred.get("has_tools") and not req.tools:
        return False
    if pred.get("has_images") and not _has_images(req):
        return False
    return True


def _resolve_target(
    target: dict[str, Any], candidates: list[ProviderModel]
) -> ProviderModel | None:
    provider = target.get("provider")
    model_id = target.get("model_id")
    for c in candidates:
        if c.provider == provider and c.model_id == model_id and c.healthy:
            return c
    return None


class CustomRulesStrategy(RoutingStrategy):
    name = "custom_rules"

    def pick(
        self,
        req: LLMRequest,
        candidates: list[ProviderModel],
        ctx: RoutingCtx,
    ) -> ProviderModel:
        if not candidates:
            raise RoutingError("no candidates")
        rules = ctx.rules.get("rules") or []
        for rule in rules:
            cond = rule.get("if") or {}
            target = rule.get("then") or {}
            if _matches(cond, req):
                resolved = _resolve_target(target, candidates)
                if resolved is not None:
                    return resolved
        fallback = ctx.rules.get("fallback") or {}
        resolved = _resolve_target(fallback, candidates)
        if resolved is not None:
            return resolved
        # Last resort: first healthy candidate.
        for c in candidates:
            if c.healthy:
                return c
        raise RoutingError("no rule matched and no healthy fallback")
