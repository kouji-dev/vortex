"""Answer generation: streaming LLM answers with inline numeric citations,
refusal gate, multi-turn rewrite."""

from ai_portal.rag.answer.citations import (
    Citation,
    CitationTracker,
    inject_citation_markers,
)
from ai_portal.rag.answer.service import (
    AnswerOptions,
    AnswerRequest,
    AnswerResult,
    answer_stream,
)

__all__ = [
    "Citation",
    "CitationTracker",
    "inject_citation_markers",
    "AnswerOptions",
    "AnswerRequest",
    "AnswerResult",
    "answer_stream",
]
