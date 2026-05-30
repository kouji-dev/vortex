"""Resolve a canonical LLM adapter for an org + model.

Bridges the per-org :class:`ProviderCredential` store and the adapter
:mod:`registry`. The facade's ``resolve_provider`` hook and the compat
``get_llm_provider`` dep both call :func:`resolve_provider_for` so there is one
place that decides *which* concrete adapter services a request.

Resolution order for a given ``(org_id, model)``:

1. Infer the provider *kind* from the model id prefix
   (``claude-*`` → anthropic, ``gpt-*``/``o*`` → openai, or explicit
   ``provider:model`` / ``provider-model`` forms).
2. Look up the org's :class:`ProviderCredential` for that kind, decrypt the
   secret, and build the adapter via :func:`registry.build_from_secret`.
3. If no per-org credential row exists, fall back to env-config keys
   (``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``) via
   :func:`registry.build_from_settings`.

Adapters are cached per ``(org_id, kind, key_fingerprint)`` so repeated calls
reuse one httpx client pool. The cache keys on a short fingerprint of the
secret (never the secret itself) so credential rotation invalidates cleanly.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from ai_portal.gateway.providers.registry import (
    ProviderNotRegistered,
    build_from_secret,
    build_from_settings,
)

logger = logging.getLogger(__name__)


class NoProviderCredential(RuntimeError):
    """Raised when neither a per-org credential nor an env key is available."""


# model-id prefix → provider kind. Longest-prefix-first at lookup time.
_PREFIX_MAP: list[tuple[str, str]] = [
    ("anthropic-claude-", "anthropic"),
    ("claude-", "anthropic"),
    ("claude/", "anthropic"),
    ("gpt-", "openai"),
    ("openai-gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("chatgpt-", "openai"),
]


def infer_provider_kind(model: str) -> str:
    """Infer the provider kind from a model id.

    Honors the explicit ``provider:model`` form first (``openai:gpt-5.4``),
    then a ``provider-...`` slug, then the prefix map. Raises ``KeyError``
    when nothing matches so callers surface a clear error.
    """
    m = (model or "").strip().lower()
    if ":" in m:
        return m.split(":", 1)[0]
    for prefix, kind in sorted(_PREFIX_MAP, key=lambda kv: -len(kv[0])):
        if m.startswith(prefix):
            return kind
    raise KeyError(f"cannot infer provider kind from model {model!r}")


def _fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


class ProviderResolver:
    """Caches adapters per ``(org, kind, key-fingerprint)``.

    Holds a ``settings`` snapshot for the env-config fallback and a callable
    that loads a decrypted org secret (injected so this module stays free of
    a hard DB-session import; ``main.py`` wires the real loader).
    """

    def __init__(
        self,
        *,
        settings: Any,
        load_org_secret: Any = None,
    ) -> None:
        self._settings = settings
        # load_org_secret(org_id, provider) -> str | None
        self._load_org_secret = load_org_secret
        self._cache: dict[tuple[str, str, str], Any] = {}

    def resolve(self, *, org_id: UUID, model: str) -> Any:
        """Return a built adapter for the org + model, building/caching it."""
        kind = infer_provider_kind(model)

        secret: str | None = None
        if self._load_org_secret is not None:
            try:
                secret = self._load_org_secret(org_id, kind)
            except Exception:  # noqa: BLE001
                logger.debug("org secret lookup failed for %s/%s", org_id, kind)
                secret = None

        if secret:
            key = (str(org_id), kind, _fingerprint(secret))
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            adapter = build_from_secret(provider=kind, api_key=secret)
            self._cache[key] = adapter
            return adapter

        # Env-config fallback (dev / internal callers without per-org creds).
        env_key = ("__env__", kind, "")
        cached = self._cache.get(env_key)
        if cached is not None:
            return cached
        try:
            adapter = build_from_settings(provider=kind, settings=self._settings)
        except (ValueError, ProviderNotRegistered) as exc:
            raise NoProviderCredential(
                f"no credential for provider {kind!r} (org={org_id}) and no "
                f"env-config fallback: {exc}"
            ) from exc
        self._cache[env_key] = adapter
        return adapter

    def clear(self) -> None:
        self._cache.clear()


__all__ = [
    "NoProviderCredential",
    "ProviderResolver",
    "infer_provider_kind",
]
