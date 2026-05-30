"""KB provider-settings validation + apply (deploy-vs-runtime enforcement).

KB settings (embedder, vector backend, reranker, chunker, retrieval policy,
language) are *runtime* state. Per the suite deploy-vs-runtime split, the UI may
only **select from** the deployment-declared + enabled set — never a free-form
value. This module is the single chokepoint that enforces that rule before any
KB row is mutated.

- embedder / vector_backend / reranker / web search default → validated against
  :mod:`ai_portal.rag.provider_config` (YAML/env declared set).
- chunker → validated against the bundled chunker registry (code-level set; not
  a deploy-config layer in the spec table).
- retrieval policy / language → free-form scalars, length-bounded only.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KnowledgeBase
from ai_portal.rag import provider_config as pc


class InvalidKbSetting(ValueError):
    """Raised when a KB setting value is not selectable from the declared set."""


def _chunker_ids() -> tuple[str, ...]:
    """Bundled chunker ids (code-level registry, not deploy-config)."""
    from ai_portal.rag.chunkers.registry import register_builtins

    return tuple(register_builtins().names())


@dataclass(frozen=True)
class KbSettingsUpdate:
    """Validated, normalised KB settings patch (only set fields are applied)."""

    embedder_id: str | None = None
    vector_backend: str | None = None
    reranker_id: str | None = None
    chunker_id: str | None = None
    default_retrieval_policy_id: str | None = None
    language: str | None = None


def validate_settings_patch(
    *,
    embedder_id: str | None = None,
    vector_backend: str | None = None,
    reranker_id: str | None = None,
    chunker_id: str | None = None,
    default_retrieval_policy_id: str | None = None,
    language: str | None = None,
    cfg: pc.ProviderConfig | None = None,
) -> KbSettingsUpdate:
    """Validate each provided field against the declared set. Raise on violation.

    Only non-``None`` fields are validated/applied. ``reranker_id`` is stored in
    ``settings_json`` by the caller (no dedicated column).
    """
    cfg = cfg or pc.get_provider_config()

    if embedder_id is not None:
        _require(pc.EMBEDDERS, embedder_id, cfg)
    if vector_backend is not None:
        _require(pc.VECTOR_STORES, vector_backend, cfg)
    if reranker_id is not None:
        _require(pc.RERANKERS, reranker_id, cfg)
    if chunker_id is not None:
        allowed = _chunker_ids()
        if chunker_id not in allowed:
            raise InvalidKbSetting(
                f"{chunker_id!r} is not a known chunker (set: {', '.join(allowed)})"
            )
    if language is not None and len(language) > 8:
        raise InvalidKbSetting("language code too long (max 8)")
    if (
        default_retrieval_policy_id is not None
        and len(default_retrieval_policy_id) > 64
    ):
        raise InvalidKbSetting("retrieval policy id too long (max 64)")

    return KbSettingsUpdate(
        embedder_id=embedder_id,
        vector_backend=vector_backend,
        reranker_id=reranker_id,
        chunker_id=chunker_id,
        default_retrieval_policy_id=default_retrieval_policy_id,
        language=language,
    )


def _require(layer: str, value: str, cfg: pc.ProviderConfig) -> None:
    try:
        pc.ensure_selectable(layer, value, cfg=cfg)
    except pc.ProviderNotSelectable as exc:
        raise InvalidKbSetting(str(exc)) from exc


def apply_settings(
    db: Session, kb: KnowledgeBase, patch: KbSettingsUpdate
) -> KnowledgeBase:
    """Persist a validated settings patch onto the KB row. Caller commits."""
    if patch.embedder_id is not None:
        kb.embedder_id = patch.embedder_id
    if patch.vector_backend is not None:
        kb.vector_backend = patch.vector_backend
    if patch.chunker_id is not None:
        kb.chunker_id = patch.chunker_id
    if patch.default_retrieval_policy_id is not None:
        kb.default_retrieval_policy_id = patch.default_retrieval_policy_id
    if patch.language is not None:
        kb.language = patch.language
    if patch.reranker_id is not None:
        # No dedicated column — reranker lives in settings_json.
        settings = dict(kb.settings_json or {})
        settings["reranker_id"] = patch.reranker_id
        kb.settings_json = settings
    db.commit()
    db.refresh(kb)
    return kb


__all__ = [
    "InvalidKbSetting",
    "KbSettingsUpdate",
    "apply_settings",
    "validate_settings_patch",
]
