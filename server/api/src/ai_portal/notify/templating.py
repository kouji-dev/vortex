"""Jinja2 loader for notification templates.

Templates live in ``ai_portal/notify/templates/`` as ``<id>.<part>.j2``.
Parts: ``subject`` (single line, optional), ``body`` (required).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=False,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render(template_id: str, part: str, payload: dict) -> str:
    """Render ``<template_id>.<part>.j2`` with payload.

    Raises:
        KeyError: template file missing.
    """
    name = f"{template_id}.{part}.j2"
    try:
        tpl = env().get_template(name)
    except TemplateNotFound as e:
        raise KeyError(f"notify template not found: {name}") from e
    return tpl.render(**payload).strip()


def has_template(template_id: str, part: str = "body") -> bool:
    return (_TEMPLATES_DIR / f"{template_id}.{part}.j2").is_file()
