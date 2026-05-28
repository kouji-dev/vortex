"""Streaming RAG answer service.

Flow:
    1. Resolve actor + KB scope.
    2. (Optional) rewrite question with prior turns.
    3. Hybrid (or federated) retrieval.
    4. Refusal gate → return policy.refusal_text if low confidence.
    5. Register citations.
    6. Build a strict system prompt + grounded context block.
    7. Stream tokens from the LLM (gateway.complete); yield text deltas
       with progressive ``[N]`` markers + a final citations payload.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable, Iterator

from ai_portal.rag.answer.citations import (
    Citation,
    CitationTracker,
    inject_citation_markers,
    used_marker_indices,
)
from ai_portal.rag.answer.refusal import RefusalPolicy, should_refuse
from ai_portal.rag.answer.rewrite import ChatTurn, rewrite_question
from ai_portal.rag.answer.summarize import compress_history
from ai_portal.rag.search.federated import FederatedRequest, federated_search
from ai_portal.rag.search.hybrid import hybrid_search
from ai_portal.rag.search.types import SearchFilter, SearchHit, SearchRequest

log = logging.getLogger(__name__)


@dataclass
class AnswerOptions:
    max_tokens: int = 800
    temperature: float = 0.2
    tone: str = "neutral"  # neutral | formal | friendly
    language: str | None = None
    answer_length: str = "medium"  # short | medium | long
    model: str = "gpt-4o-mini"
    # Multi-turn history compression
    history_threshold_turns: int = 6
    history_keep_recent: int = 4
    history_budget_tokens: int = 4_000


@dataclass
class AnswerRequest:
    query: str
    kb_ids: list[int]
    actor_user_id: str | None = None
    actor_group_ids: tuple[str, ...] = ()
    prior_turns: list[ChatTurn] = field(default_factory=list)
    filter: SearchFilter = field(default_factory=SearchFilter)
    top_k: int = 8
    federated: bool = False
    options: AnswerOptions = field(default_factory=AnswerOptions)
    refusal: RefusalPolicy = field(default_factory=RefusalPolicy)


@dataclass
class AnswerResult:
    """Final answer payload after the stream completes."""

    text: str
    citations: list[Citation]
    refused: bool
    used_indices: list[int]
    rewritten_query: str


# ---------------------------------------------------------------------------
# System prompt (caveman style — per project CLAUDE.md)
# ---------------------------------------------------------------------------


def _build_system_prompt(opts: AnswerOptions) -> str:
    parts = [
        "Answer mode: grounded RAG.",
        "- Use only the provided CONTEXT.",
        "- Cite sources inline as [1], [2] referring to CONTEXT entries.",
        "- If CONTEXT lacks the answer, say so. Do not invent.",
    ]
    if opts.tone == "formal":
        parts.append("- Tone: formal.")
    elif opts.tone == "friendly":
        parts.append("- Tone: friendly.")
    if opts.language:
        parts.append(f"- Reply in: {opts.language}.")
    if opts.answer_length == "short":
        parts.append("- Keep answer under 80 words.")
    elif opts.answer_length == "long":
        parts.append("- Allow up to 400 words. Use short sections.")
    else:
        parts.append("- Aim for 150-250 words.")
    return "\n".join(parts)


def _build_context_block(citations: list[Citation]) -> str:
    """Render numbered CONTEXT block consumed by the model."""
    rows = []
    for c in citations:
        rows.append(f"[{c.index}] {c.title}\n{c.snippet}")
    return "CONTEXT:\n" + "\n\n".join(rows)


# ---------------------------------------------------------------------------
# Retrieval + assembly (sync helpers that the streamer composes)
# ---------------------------------------------------------------------------


def _retrieve(db, req: AnswerRequest) -> list[SearchHit]:
    if req.federated:
        fed = FederatedRequest(
            query=req.query,
            kb_ids=req.kb_ids,
            top_k=req.top_k,
            filter=req.filter,
        )
        return federated_search(db, fed)
    sub = SearchRequest(
        query=req.query,
        kb_ids=req.kb_ids,
        top_k=req.top_k,
        filter=req.filter,
        actor_user_id=req.actor_user_id,
        actor_group_ids=req.actor_group_ids,
    )
    return hybrid_search(db, sub)


# ---------------------------------------------------------------------------
# Streamer protocol
# ---------------------------------------------------------------------------

# Caller-supplied LLM streamer: (system, user, opts) -> iterable of text chunks.
StreamFn = Any


def _default_stream(system: str, user: str, opts: AnswerOptions) -> Iterable[str]:
    """Stream completion via Gateway facade when available; else single non-stream call."""
    try:  # pragma: no cover - gateway absent in this branch
        from ai_portal.gateway import stream_complete  # type: ignore

        for chunk in stream_complete(
            model=opts.model,
            system=system,
            user=user,
            max_tokens=opts.max_tokens,
            temperature=opts.temperature,
        ):
            yield chunk
        return
    except Exception:  # noqa: BLE001
        pass
    try:  # pragma: no cover
        from ai_portal.gateway import complete  # type: ignore

        res = complete(model=opts.model, system=system, user=user)
        yield getattr(res, "text", str(res))
    except Exception:  # noqa: BLE001
        # Last-resort echo so streaming infra is exercisable.
        yield "I don't have the source-grounded model wired up."


# ---------------------------------------------------------------------------
# Public sync iterator API
# ---------------------------------------------------------------------------


@dataclass
class AnswerEvent:
    kind: str  # "delta" | "citation" | "refusal" | "final"
    text: str | None = None
    citation: Citation | None = None
    result: AnswerResult | None = None


def answer_stream(
    db,
    req: AnswerRequest,
    *,
    stream_fn: StreamFn | None = None,
    rewrite_fn: Any | None = None,
    summarize_fn: Any | None = None,
) -> Iterator[AnswerEvent]:
    """Generator yielding answer events.

    Caller is responsible for adapting this to SSE/HTTP. `stream_fn`,
    `rewrite_fn`, and `summarize_fn` are injectable for tests.
    """
    # 0. Compress older turns when history exceeds threshold.
    compressed = compress_history(
        req.prior_turns,
        threshold_turns=req.options.history_threshold_turns,
        keep_recent=req.options.history_keep_recent,
        budget_tokens=req.options.history_budget_tokens,
        model=req.options.model,
        complete_fn=summarize_fn,
    )
    # The rewrite stage only needs the recent verbatim turns; the summary
    # is injected as a synthetic "system" turn so coreferences still resolve.
    rewrite_turns: list[ChatTurn] = []
    if compressed.compressed and compressed.summary:
        rewrite_turns.append(ChatTurn(role="system", text=f"prior_summary: {compressed.summary}"))
    rewrite_turns.extend(compressed.recent)

    # 1. Rewrite for multi-turn context.
    rewritten = rewrite_question(
        req.query, rewrite_turns, model=req.options.model, complete_fn=rewrite_fn
    )

    # 2. Retrieval.
    retrieve_req = AnswerRequest(
        query=rewritten,
        kb_ids=req.kb_ids,
        actor_user_id=req.actor_user_id,
        actor_group_ids=req.actor_group_ids,
        prior_turns=[],
        filter=req.filter,
        top_k=req.top_k,
        federated=req.federated,
        options=req.options,
        refusal=req.refusal,
    )
    hits = _retrieve(db, retrieve_req)

    # 3. Refusal gate.
    if should_refuse(hits, req.refusal):
        text = req.refusal.refusal_text
        yield AnswerEvent(kind="refusal", text=text)
        yield AnswerEvent(
            kind="final",
            result=AnswerResult(
                text=text,
                citations=[],
                refused=True,
                used_indices=[],
                rewritten_query=rewritten,
            ),
        )
        return

    # 4. Citations.
    tracker = CitationTracker()
    citations = tracker.register_all(hits)
    for c in citations:
        yield AnswerEvent(kind="citation", citation=c)

    # 5. Prompt assembly.
    system = _build_system_prompt(req.options)
    context = _build_context_block(citations)
    user = f"{context}\n\nQUESTION: {rewritten}"

    # 6. Stream from LLM.
    fn = stream_fn or _default_stream
    collected: list[str] = []
    for chunk in fn(system, user, req.options):
        if not chunk:
            continue
        collected.append(chunk)
        yield AnswerEvent(kind="delta", text=chunk)

    final_text = "".join(collected).strip()
    final_text = inject_citation_markers(
        final_text, fallback_indices=[c.index for c in citations[:2]]
    )
    used = used_marker_indices(final_text)
    yield AnswerEvent(
        kind="final",
        result=AnswerResult(
            text=final_text,
            citations=citations,
            refused=False,
            used_indices=used,
            rewritten_query=rewritten,
        ),
    )


async def answer_stream_async(
    db, req: AnswerRequest, **kwargs
) -> AsyncIterator[AnswerEvent]:
    """Async wrapper for FastAPI SSE handlers."""
    for ev in answer_stream(db, req, **kwargs):
        yield ev
