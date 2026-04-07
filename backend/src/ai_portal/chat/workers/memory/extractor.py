# Re-export shim — canonical implementation lives in workers/memory/extractor.py
from ai_portal.workers.memory.extractor import *  # noqa: F401, F403
from ai_portal.workers.memory.extractor import (  # noqa: F401
    _call_system_profile_llm,
    SystemProfileUpdate,
    extract_user_memories,
)
