# Re-export shim — real implementation moved to core/config.py
from ai_portal.core.config import *  # noqa: F401, F403
from ai_portal.core.config import Settings, get_settings, settings_log_snapshot
