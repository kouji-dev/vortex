"""Identity Provider (SSO) abstraction.

Each org may attach one or more IdP connections. Each IdP implementation
satisfies the :class:`IdentityProvider` protocol (``initiate`` + ``complete``).

Providers are registered via :func:`register_provider` and resolved by name
through :func:`get_provider`. Bundled providers under ``providers/`` (OIDC,
SAML) register themselves on import.

SSO routes and the org-level "sso_required" enforcement live elsewhere
(Phase G5 / G6) — this subpackage is the substrate only.
"""

from ai_portal.auth.idp.model import IdpConnection
from ai_portal.auth.idp.protocol import IdentityProvider, UserClaims
from ai_portal.auth.idp.registry import (
    IdpProviderFactory,
    IdpProviderNotFound,
    available_providers,
    get_provider,
    register_provider,
)

__all__ = [
    "IdentityProvider",
    "IdpConnection",
    "IdpProviderFactory",
    "IdpProviderNotFound",
    "UserClaims",
    "available_providers",
    "get_provider",
    "register_provider",
]
