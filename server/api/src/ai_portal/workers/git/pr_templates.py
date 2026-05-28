"""Per-pool PR template — interpolate title/body with run context.

Stored on ``WorkerPool.settings_json.pr_template``. Schema::

    {
      "title_format": str,         # may reference {title} {task_id} {branch} {repo}
      "description_format": str,   # may reference {summary} {task_id} {branch} {repo}
      "test_plan": str,            # optional; appended as ## Test Plan section
      "generated_by_tag": str,     # optional; appended as footer line
    }

Unknown ``{placeholders}`` are kept literal so a typo never crashes a run.
"""

from __future__ import annotations

from typing import TypedDict


class PrTemplate(TypedDict, total=False):
    title_format: str
    description_format: str
    test_plan: str
    generated_by_tag: str


_DEFAULT_TITLE = "{title}"
_DEFAULT_BODY = "{summary}"


def _safe_format(tpl: str, vars: dict[str, str]) -> str:
    """``str.format_map`` with missing keys preserved as literal ``{key}``."""

    class _Default(dict):
        def __missing__(self, key: str) -> str:  # type: ignore[override]
            return "{" + key + "}"

    return tpl.format_map(_Default(vars))


def apply_template(
    tpl: PrTemplate | None,
    *,
    title: str,
    body: str,
    task_id: str,
    branch: str,
    repo: str,
    summary: str,
) -> dict[str, str]:
    """Format a PR title/body using ``tpl``. Returns ``{title, body}``."""
    if tpl is None:
        return {"title": title, "body": body}

    vars = {
        "title": title,
        "task_id": task_id,
        "branch": branch,
        "repo": repo,
        "summary": summary,
    }
    t_fmt = tpl.get("title_format") or _DEFAULT_TITLE
    b_fmt = tpl.get("description_format") or _DEFAULT_BODY

    out_title = _safe_format(t_fmt, vars)
    out_body = _safe_format(b_fmt, vars)

    test_plan = tpl.get("test_plan")
    if test_plan:
        out_body = out_body + "\n\n## Test Plan\n" + test_plan.strip()

    tag = tpl.get("generated_by_tag")
    if tag:
        out_body = out_body + "\n\n---\n" + tag.strip()

    return {"title": out_title, "body": out_body}
