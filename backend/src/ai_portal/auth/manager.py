# Re-export shim — real implementation moved to auth/strategies/dev.py
from ai_portal.auth.strategies.dev import (  # noqa: F401
    UserManager,
    AuthenticationError,
    RegistrationError,
)
