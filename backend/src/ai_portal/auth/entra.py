# Re-export shim — real implementation moved to auth/strategies/entra.py
from ai_portal.auth.strategies.entra import (  # noqa: F401
    decode_entra_access_token,
    roles_from_claims,
)
