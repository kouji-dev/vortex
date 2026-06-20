"""Bundled IdP provider implementations.

Each bundled module registers itself in the global IdP registry via
:func:`ai_portal.auth.idp.registry.register_provider` at import time. Apps
that want SSO must import this package once during startup.
"""

# Side-effect imports — each module calls register_provider() at load time.
from ai_portal.auth.idp.providers import (  # noqa: F401
    google,
    oidc,
    okta,
    saml,
)

