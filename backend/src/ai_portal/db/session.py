# Re-export shim — real implementation moved to core/db/session.py
from ai_portal.core.db.session import *  # noqa: F401, F403
from ai_portal.core.db.session import SessionLocal, engine
