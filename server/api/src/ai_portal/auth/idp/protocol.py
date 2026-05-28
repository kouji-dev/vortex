"""IdentityProvider protocol — minimum interface every IdP must implement.

Routes call ``initiate`` to start an SSO handshake (returns redirect URL) and
``complete`` to finish it (returns the verified user claims). The protocol is
narrow on purpose: provider-specific config (client_id, metadata XML, etc.)
lives inside the provider instance, not in the protocol shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class UserClaims:
    """Verified identity returned by ``IdentityProvider.complete``.

    ``subject`` is the IdP's stable user identifier (OIDC ``sub``, SAML
    ``NameID``). ``email`` is the verified email. ``raw`` holds the full claim
    bag for callers that need provider-specific fields.
    """

    subject: str
    email: str
    name: str | None = None
    groups: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IdentityProvider(Protocol):
    """Single-org SSO provider instance.

    Implementations are typically constructed from an :class:`IdpConnection`
    row via a factory registered in ``registry.py``.
    """

    name: str

    async def initiate(self, *, state: str, redirect_uri: str) -> str:
        """Return the URL the browser should be redirected to."""
        ...

    async def complete(self, *, params: dict[str, Any], state: str) -> UserClaims:
        """Validate the IdP response and return verified claims.

        ``params`` is the parsed body/query of the callback. ``state`` is the
        opaque value the caller stored before ``initiate`` so the provider can
        cross-check (PKCE verifier lookup, replay protection, etc.).
        """
        ...
