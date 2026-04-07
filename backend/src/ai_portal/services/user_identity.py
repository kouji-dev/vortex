# Re-export shim — real implementation moved to auth/service.py
from ai_portal.auth.service import (  # noqa: F401
    profile_fields_from_claims,
    email_from_claims,
    upsert_user_from_entra_claims,
)
