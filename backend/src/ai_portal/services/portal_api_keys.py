# Re-export shim — real implementation moved to auth/strategies/portal_keys.py
from ai_portal.auth.strategies.portal_keys import (  # noqa: F401
    hash_portal_api_key,
    create_portal_api_key,
    user_for_portal_api_key,
    list_keys_for_user,
    revoke_key,
)
