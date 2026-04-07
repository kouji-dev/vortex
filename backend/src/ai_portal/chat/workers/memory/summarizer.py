# Re-export shim — canonical implementation lives in workers/memory/summarizer.py
from ai_portal.workers.memory.summarizer import *  # noqa: F401, F403
from ai_portal.workers.memory.summarizer import (  # noqa: F401
    _call_summary_llm,
    _format_transcript,
    summarize_conversation,
)
