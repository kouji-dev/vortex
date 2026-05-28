"""Gateway rate limits — token-bucket per (scope, dimension).

Public surface:

- :class:`RateLimitRule` — SQLAlchemy ORM model.
- :class:`RateLimitService` — CRUD + ``check_rate_limit`` orchestrator.
- :class:`TokenBucket` — backend-agnostic bucket interface.
- :class:`InMemoryBucket`, :class:`RedisBucket` — bundled backends.
- :exc:`RateLimitExceeded` — raised on 429.
- :class:`Dimension` — Literal["rpm", "tpm", "concurrent_requests"].
- :func:`check_rate_limit` — FastAPI-friendly dep helper.
"""

from __future__ import annotations

from ai_portal.gateway.rate_limits.bucket import (
    InMemoryBucket,
    RedisBucket,
    TokenBucket,
    build_bucket,
)
from ai_portal.gateway.rate_limits.model import RateLimitRule
from ai_portal.gateway.rate_limits.service import (
    Dimension,
    LimitView,
    RateLimitExceeded,
    RateLimitService,
    check_rate_limit,
)

__all__ = [
    "Dimension",
    "InMemoryBucket",
    "LimitView",
    "RateLimitExceeded",
    "RateLimitRule",
    "RateLimitService",
    "RedisBucket",
    "TokenBucket",
    "build_bucket",
    "check_rate_limit",
]
