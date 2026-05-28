"""Tests for trace correlation helpers."""

from __future__ import annotations

from ai_portal.workers.observability.trace_link import (
    build_trace_actor,
    extract_task_id,
    metric_tags,
    task_id_filter,
)


def test_build_actor_minimum() -> None:
    a = build_trace_actor(org_id="o", user_id=None, task_id="t-1")
    assert a == {"kind": "worker", "org_id": "o", "task_id": "t-1"}


def test_build_actor_full() -> None:
    a = build_trace_actor(
        org_id="o", user_id="u", task_id="t-1", run_id="r-1",
    )
    assert a["user_id"] == "u"
    assert a["run_id"] == "r-1"
    assert a["task_id"] == "t-1"
    assert a["kind"] == "worker"


def test_build_actor_override_kind() -> None:
    a = build_trace_actor(org_id="o", user_id=None, task_id="t", actor_type="system")
    assert a["kind"] == "system"


def test_extract_task_id_roundtrip() -> None:
    actor = build_trace_actor(org_id="o", user_id=None, task_id="abc")
    assert extract_task_id(actor) == "abc"


def test_extract_task_id_missing_returns_none() -> None:
    assert extract_task_id(None) is None
    assert extract_task_id({}) is None
    assert extract_task_id({"task_id": ""}) is None


def test_metric_tags_drops_none_values() -> None:
    t = metric_tags(org_id="o", pool_id=None, template=None, repo=None)
    assert t == {"org_id": "o"}


def test_metric_tags_full() -> None:
    t = metric_tags(
        org_id="o", pool_id="p", template="python", repo="acme/api",
    )
    assert t == {
        "org_id": "o",
        "pool_id": "p",
        "template": "python",
        "repo": "acme/api",
    }


def test_task_id_filter_builds_jsonb_path_expression() -> None:
    """Validate that the filter helper builds the right expression shape.

    We use a tiny stub class instead of importing the real RequestTrace —
    avoids needing the gateway model imported in this unit test.
    """

    class _Col:
        def __init__(self, name):
            self.name = name

        def __getitem__(self, key):
            return _Indexed(self.name, key)

    class _Indexed:
        def __init__(self, base, key):
            self.base, self.key = base, key

        @property
        def astext(self):
            return _Compare(self.base, self.key)

    class _Compare:
        def __init__(self, base, key):
            self.base, self.key = base, key
            self.equals = None

        def __eq__(self, other):
            return ("eq", self.base, self.key, other)

    class _Stub:
        actor_json = _Col("actor_json")

    expr = task_id_filter(_Stub, "task-42")
    assert expr == ("eq", "actor_json", "task_id", "task-42")
