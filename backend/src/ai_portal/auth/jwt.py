# Re-export shim — real implementation moved to auth/strategies/jwt.py
from ai_portal.auth.strategies.jwt import (  # noqa: F401
    create_access_token,
    create_refresh_token,
    decode_token,
)
