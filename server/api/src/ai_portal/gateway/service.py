"""Gateway dispatch service — minimal facade for the compat surfaces.

Provides:

- :func:`get_llm_provider` — FastAPI dep that resolves the active provider.
  Tests override this dep with a fake provider. Future routing / failover /
  guardrails / cache logic will land here.
- :func:`complete` / :func:`stream` / :func:`embed` — thin async wrappers that
  delegate to the provider's canonical protocol methods.
- :class:`PolicyResolver` — resolves guardrail policy per request using the
  precedence ``key scope → route default → org default``. Cached per
  :class:`PolicyResolutionRequest` so input + output checks share one fetch.

This is intentionally tiny. Phase C (routing) + Phase E (cache) + Phase F
(guardrails) hook in by replacing :func:`get_llm_provider` and wrapping the
provider call in this module.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    LLMRequest,
    LLMResponse,
    StreamChunk,
)


@runtime_checkable
class _ProviderLike(Protocol):
    """Structural shape the gateway needs from a provider.

    Matches :class:`ai_portal.catalog.providers.protocol.LLMProvider` but
    declared here as a Protocol to avoid an import cycle and to let tests
    inject lightweight fakes without inheriting from the full LLMProvider.
    """

    name: str
    capabilities: set[Capability]

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse: ...
    async def stream_canonical(self, req: LLMRequest) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, texts: list[str], model: str) -> Embeddings: ...


def get_llm_provider() -> _ProviderLike:
    """FastAPI dep — yields the LLMProvider that will service the request.

    The default raises so production wiring is forced to override this dep
    (routing/credentials live in higher phases). Tests override with a fake.
    """
    raise RuntimeError(
        "no LLMProvider bound — override `get_llm_provider` in tests or wire "
        "routing.resolve_provider() in production startup."
    )


async def complete(req: LLMRequest, provider: _ProviderLike) -> LLMResponse:
    """Non-streaming completion dispatch."""
    return await provider.complete_canonical(req)


async def stream(
    req: LLMRequest, provider: _ProviderLike
) -> AsyncIterator[StreamChunk]:
    """Streaming completion dispatch."""
    async for chunk in provider.stream_canonical(req):
        yield chunk


async def embed(
    texts: list[str], model: str, provider: _ProviderLike
) -> Embeddings:
    """Embeddings dispatch."""
    return await provider.embed(texts, model)


# ── guardrail policy resolution ─────────────────────────────────────────────


class PolicySource(str, Enum):
    """Which layer supplied the resolved guardrail policy."""

    KEY = "key"
    ROUTE = "route"
    ORG = "org"


@dataclass(frozen=True)
class PolicyResolutionRequest:
    """Inputs to :meth:`PolicyResolver.resolve` — also the cache key."""

    org_id: uuid.UUID
    route: str
    key_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ResolvedPolicy:
    """Resolved guardrail policy for one request."""

    policy_id: uuid.UUID
    source: PolicySource
    policy: dict[str, Any]


@runtime_checkable
class _PolicyStoreLike(Protocol):
    """Structural seam over the policy-bundle persistence layer.

    F1's concrete store (guardrails.service.PolicyStore) implements this.
    Tests inject in-memory fakes.
    """

    def get_key_policy(
        self, *, org_id: uuid.UUID, key_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    def get_route_default(
        self, *, org_id: uuid.UUID, route: str
    ) -> uuid.UUID | None: ...

    def get_org_default(self, *, org_id: uuid.UUID) -> uuid.UUID | None: ...

    def load_policy(self, policy_id: uuid.UUID) -> dict[str, Any] | None: ...


class PolicyResolver:
    """Resolves the guardrail policy for one request.

    Precedence: key scope → route default → org default. The first layer
    that yields both a policy_id AND a loadable policy wins; a dangling id
    falls through to the next layer.

    Resolutions are memoised per :class:`PolicyResolutionRequest`; build a
    fresh :class:`PolicyResolver` per HTTP request so the cache lifetime
    matches the request lifetime.
    """

    def __init__(self, store: _PolicyStoreLike) -> None:
        self._store = store
        self._cache: dict[PolicyResolutionRequest, ResolvedPolicy | None] = {}

    def resolve(self, req: PolicyResolutionRequest) -> ResolvedPolicy | None:
        if req in self._cache:
            return self._cache[req]
        result = self._resolve_uncached(req)
        self._cache[req] = result
        return result

    def _resolve_uncached(self, req: PolicyResolutionRequest) -> ResolvedPolicy | None:
        # 1. key scope
        if req.key_id is not None:
            pid = self._store.get_key_policy(org_id=req.org_id, key_id=req.key_id)
            resolved = self._try_load(pid, PolicySource.KEY)
            if resolved is not None:
                return resolved
        # 2. route default
        pid = self._store.get_route_default(org_id=req.org_id, route=req.route)
        resolved = self._try_load(pid, PolicySource.ROUTE)
        if resolved is not None:
            return resolved
        # 3. org default
        pid = self._store.get_org_default(org_id=req.org_id)
        resolved = self._try_load(pid, PolicySource.ORG)
        if resolved is not None:
            return resolved
        return None

    def _try_load(
        self, policy_id: uuid.UUID | None, source: PolicySource
    ) -> ResolvedPolicy | None:
        if policy_id is None:
            return None
        bundle = self._store.load_policy(policy_id)
        if bundle is None:
            return None
        return ResolvedPolicy(policy_id=policy_id, source=source, policy=bundle)


__all__ = [
    "PolicyResolutionRequest",
    "PolicyResolver",
    "PolicySource",
    "ResolvedPolicy",
    "complete",
    "embed",
    "get_llm_provider",
    "stream",
]
