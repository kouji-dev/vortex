"""SocialProvider protocol — consumer OAuth interface.

Narrow on purpose: provider-specific config (client_id/secret, endpoints)
lives in the provider instance. Routes call ``authorize_url`` to start the
handshake and ``exchange`` to finish it, receiving verified
:class:`~ai_portal.auth.idp.protocol.UserClaims`.

Reuses :class:`UserClaims` from the IdP layer so JIT-provisioning code is shared
across social + enterprise sign-in.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ai_portal.auth.idp.protocol import UserClaims

__all__ = ["SocialProvider", "UserClaims"]


@runtime_checkable
class SocialProvider(Protocol):
    """Consumer OAuth provider instance."""

    name: str

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        """Return the URL the browser is redirected to (synchronous build)."""
        ...

    async def exchange(
        self, *, params: dict[str, Any], state: str, redirect_uri: str
    ) -> UserClaims:
        """Exchange the callback code for a token, return verified claims.

        ``params`` is the parsed callback query (``code``, ``state``).
        Implementations must reject a ``state`` mismatch.
        """
        ...
