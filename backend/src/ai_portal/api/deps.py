# Re-export shim — real implementation moved to auth/deps.py
from ai_portal.auth.deps import (  # noqa: F401
    get_db,
    get_current_user,
    get_app_roles,
    get_current_org_id,
)
