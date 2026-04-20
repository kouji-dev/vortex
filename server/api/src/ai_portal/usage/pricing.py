"""Deprecated location — use ai_portal.chat.llm_pricing and ai_portal.chat.cost_calculator.

Kept during Phase 3–8 transition. Deleted in Phase 12.
"""
from ai_portal.chat.llm_pricing import LlmRate, get_llm_rates  # noqa: F401
from ai_portal.chat.cost_calculator import compute_llm_cost  # noqa: F401
