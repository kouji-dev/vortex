"""Gateway evals — test-set CRUD + multi-model runs + judges.

Public surface:

- :class:`ModelEval`, :class:`ModelEvalRun` — SQLAlchemy ORM models.
- :class:`EvalsService` — CRUD + ``run_eval`` orchestrator.
- :class:`EvalRunner` — pure execution (per-model fan-out + scoring).
- :class:`JudgeVerdict` — judge return shape.
- :func:`exact_judge`, :func:`regex_judge`, :func:`llm_judge`,
  :func:`custom_judge`, :func:`register_custom_judge` — bundled judges.
"""

from __future__ import annotations

from ai_portal.gateway.evals.judges import (
    JudgeVerdict,
    custom_judge,
    exact_judge,
    llm_judge,
    regex_judge,
    register_custom_judge,
)
from ai_portal.gateway.evals.model import ModelEval, ModelEvalRun
from ai_portal.gateway.evals.runner import EvalRunner, RunOutcome
from ai_portal.gateway.evals.service import (
    EvalRunView,
    EvalsService,
    EvalView,
)

__all__ = [
    "EvalRunView",
    "EvalRunner",
    "EvalView",
    "EvalsService",
    "JudgeVerdict",
    "ModelEval",
    "ModelEvalRun",
    "RunOutcome",
    "custom_judge",
    "exact_judge",
    "llm_judge",
    "regex_judge",
    "register_custom_judge",
]
