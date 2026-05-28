"""Memory extractor protocol, registry, and bundled implementations.

Importing this package eagerly registers bundled extractors (no_op,
rule_based, llm_default, llm_typed).
"""
from __future__ import annotations

from .protocol import Candidate, ExtractOpts, ExtractScope, Extractor, Turn
from .registry import get, list_names, register

# Eager registration of bundled extractors.
from . import no_op  # noqa: F401
from . import rule_based  # noqa: F401
from . import llm_default  # noqa: F401
from . import llm_typed  # noqa: F401

__all__ = [
    "Candidate",
    "ExtractOpts",
    "ExtractScope",
    "Extractor",
    "Turn",
    "get",
    "list_names",
    "register",
]
