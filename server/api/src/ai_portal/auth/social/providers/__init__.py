"""Bundled social providers — import to register them.

Importing this package registers ``google`` and ``github`` factories
in the social registry. Each factory reads credentials from env and raises
``SocialProviderNotConfigured`` when they are absent, so unconfigured providers
are never advertised.
"""

from ai_portal.auth.social.providers import (
    github,  # noqa: F401
    google,  # noqa: F401
)
