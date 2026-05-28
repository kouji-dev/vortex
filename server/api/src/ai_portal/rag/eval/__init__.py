"""RAG eval framework.

Test sets per KB, runners that score retrieval (recall@k, MRR, nDCG) and
answer quality (LLM-as-judge: correctness + faithfulness), and regression
detection that emits ``kb.eval.regression`` webhooks.
"""
from ai_portal.rag.eval.metrics import mrr, ndcg_at_k, recall_at_k
from ai_portal.rag.eval.runner import EvalRunner, RunOutcome
from ai_portal.rag.eval.schemas import (
    EvalRecord,
    EvalRunOut,
    EvalRunRowResult,
    EvalRunSummary,
    EvalTestSetIn,
    EvalTestSetOut,
)

__all__ = [
    "EvalRecord",
    "EvalRunOut",
    "EvalRunRowResult",
    "EvalRunSummary",
    "EvalRunner",
    "EvalTestSetIn",
    "EvalTestSetOut",
    "RunOutcome",
    "mrr",
    "ndcg_at_k",
    "recall_at_k",
]
