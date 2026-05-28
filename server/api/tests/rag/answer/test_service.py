"""End-to-end answer streaming with stubbed retrieval + stub LLM."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_portal.rag.answer.refusal import RefusalPolicy
from ai_portal.rag.answer.service import (
    AnswerOptions,
    AnswerRequest,
    AnswerResult,
    answer_stream,
)
from ai_portal.rag.search.types import SearchHit


def _hit(cid, doc, score=0.8, title=None):
    return SearchHit(
        chunk_id=cid,
        document_id=doc,
        kb_id=1,
        text=f"content for {cid}",
        score=score,
        meta={"title": title or f"Doc {cid}", "source_uri": f"https://ex/{doc}"},
    )


def _run(events_iter):
    return list(events_iter)


def _final(events):
    for ev in events:
        if ev.kind == "final":
            assert isinstance(ev.result, AnswerResult)
            return ev.result
    raise AssertionError("no final event")


def test_refusal_when_no_hits():
    db = MagicMock()
    req = AnswerRequest(query="q", kb_ids=[1])
    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=[]):
        events = _run(answer_stream(db, req, stream_fn=lambda s, u, o: ["should not run"]))
    res = _final(events)
    assert res.refused is True
    assert res.text == req.refusal.refusal_text
    assert res.citations == []
    assert any(e.kind == "refusal" for e in events)


def test_refusal_when_top_score_too_low():
    db = MagicMock()
    req = AnswerRequest(
        query="q",
        kb_ids=[1],
        refusal=RefusalPolicy(min_score=0.5, min_supporting=1),
    )
    weak = [_hit("c", "d", score=0.1)]
    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=weak):
        res = _final(_run(answer_stream(db, req, stream_fn=lambda s, u, o: [])))
    assert res.refused is True


def test_streams_citations_then_deltas_then_final():
    db = MagicMock()
    req = AnswerRequest(query="What is X?", kb_ids=[1])
    hits = [_hit("c1", "d1", title="Doc One"), _hit("c2", "d2", title="Doc Two")]

    def fake_stream(system, user, opts):
        # Verify CONTEXT block ends up in user prompt.
        assert "CONTEXT:" in user
        yield "Answer text "
        yield "with citations [1] [2]."

    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=hits):
        events = _run(answer_stream(db, req, stream_fn=fake_stream))

    kinds = [ev.kind for ev in events]
    # citation events first, then delta, then final.
    assert kinds.count("citation") == 2
    assert "delta" in kinds
    assert kinds[-1] == "final"

    res = _final(events)
    assert "Answer text" in res.text
    assert res.refused is False
    assert [c.index for c in res.citations] == [1, 2]
    assert res.used_indices == [1, 2]


def test_falls_back_to_appended_markers_when_model_omits_them():
    db = MagicMock()
    req = AnswerRequest(query="q", kb_ids=[1])
    hits = [_hit("c1", "d1"), _hit("c2", "d2")]

    def fake_stream(system, user, opts):
        yield "Answer with no markers."

    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=hits):
        res = _final(_run(answer_stream(db, req, stream_fn=fake_stream)))
    assert "[1]" in res.text
    assert "[2]" in res.text


def test_uses_federated_when_flag_set():
    db = MagicMock()
    req = AnswerRequest(query="q", kb_ids=[1, 2], federated=True)
    hits = [_hit("c1", "d1")]

    with patch("ai_portal.rag.answer.service.federated_search", return_value=hits) as fed, \
         patch("ai_portal.rag.answer.service.hybrid_search") as hyb:
        _run(answer_stream(db, req, stream_fn=lambda s, u, o: ["ok"]))
    fed.assert_called_once()
    hyb.assert_not_called()


def test_rewrite_invoked_when_prior_turns_supplied():
    db = MagicMock()
    from ai_portal.rag.answer.rewrite import ChatTurn

    req = AnswerRequest(
        query="How fast?",
        kb_ids=[1],
        prior_turns=[ChatTurn("user", "Tell me about RAG.")],
    )
    hits = [_hit("c1", "d1")]
    rewrites = []

    def rewrite_fn(system, user, model):
        rewrites.append(user)
        return "How fast is RAG?"

    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=hits) as hyb:
        res = _final(
            _run(
                answer_stream(
                    db, req, stream_fn=lambda s, u, o: ["ok"], rewrite_fn=rewrite_fn
                )
            )
        )

    assert res.rewritten_query == "How fast is RAG?"
    # Hybrid retrieval should have been called with the rewritten query.
    called_req = hyb.call_args[0][1]
    assert called_req.query == "How fast is RAG?"
    # Rewrite prompt was constructed with prior turns.
    assert rewrites and "Tell me about RAG" in rewrites[0]


def test_options_propagate_to_stream_fn():
    db = MagicMock()
    opts = AnswerOptions(model="gpt-9", temperature=0.5, max_tokens=200, tone="formal")
    req = AnswerRequest(query="q", kb_ids=[1], options=opts)
    hits = [_hit("c1", "d1")]

    captured = {}

    def fake(system, user, o):
        captured["system"] = system
        captured["opts"] = o
        yield "x"

    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=hits):
        _run(answer_stream(db, req, stream_fn=fake))

    assert "formal" in captured["system"]
    assert captured["opts"].model == "gpt-9"


def test_long_history_triggers_compression_before_rewrite():
    """When prior_turns > threshold, summarize_fn is invoked and the summary is
    injected as a synthetic system turn before rewrite."""
    db = MagicMock()
    from ai_portal.rag.answer.rewrite import ChatTurn

    long_history = [
        ChatTurn(role="user" if i % 2 == 0 else "assistant", text=f"turn-{i}")
        for i in range(12)
    ]
    req = AnswerRequest(
        query="latest q",
        kb_ids=[1],
        prior_turns=long_history,
        options=AnswerOptions(history_threshold_turns=6, history_keep_recent=4),
    )
    hits = [_hit("c1", "d1")]

    summarize_calls: list[str] = []
    rewrite_inputs: list[str] = []

    def summarize_fn(system, user, model):
        summarize_calls.append(user)
        return "Summarized older turns."

    def rewrite_fn(system, user, model):
        rewrite_inputs.append(user)
        return "rewritten question"

    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=hits):
        _run(answer_stream(
            db, req,
            stream_fn=lambda s, u, o: ["x"],
            rewrite_fn=rewrite_fn,
            summarize_fn=summarize_fn,
        ))

    # Compression ran on older turns.
    assert summarize_calls, "summarize_fn must be called once"
    assert "turn-0" in summarize_calls[0]
    # The summary becomes a synthetic "system" turn fed into rewrite.
    assert rewrite_inputs and "Summarized older turns" in rewrite_inputs[0]
    # Recent turns remain verbatim in the rewrite prompt.
    assert "turn-11" in rewrite_inputs[0]


def test_short_history_skips_compression():
    db = MagicMock()
    from ai_portal.rag.answer.rewrite import ChatTurn

    req = AnswerRequest(
        query="q",
        kb_ids=[1],
        prior_turns=[ChatTurn("user", "hi")],
        options=AnswerOptions(history_threshold_turns=6),
    )
    hits = [_hit("c1", "d1")]

    summarize_calls = []

    def summarize_fn(*a, **k):
        summarize_calls.append(a)
        return "should-not-be-called"

    with patch("ai_portal.rag.answer.service.hybrid_search", return_value=hits):
        _run(answer_stream(
            db, req,
            stream_fn=lambda s, u, o: ["x"],
            summarize_fn=summarize_fn,
        ))

    assert summarize_calls == [], "short history must not trigger summarizer"
