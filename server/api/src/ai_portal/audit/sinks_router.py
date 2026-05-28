"""SIEM sink observability — health + metrics endpoints.

GET /v1/audit/sinks/health   — per-sink last_write_at + last_error
GET /v1/audit/sinks/metrics  — per-sink p50/p95 latency + success rate

Per-process in-memory counters. For multi-instance deployments these are
node-local; aggregate at the load-balancer or shard via cookie affinity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ai_portal.audit.sinks_metrics import metrics
from ai_portal.auth.deps import get_current_user
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role

router = APIRouter(prefix="/v1/audit/sinks", tags=["audit-sinks"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


@router.get("/health")
def sinks_health(user: User = Depends(_require_admin)) -> dict:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    rows = metrics().list_org(user.org_id)
    return {
        "org_id": str(user.org_id),
        "items": [
            {
                "sink": r["sink"],
                "last_write_at": r["last_write_at"],
                "last_status": r["last_status"],
                "last_error": r["last_error"],
            }
            for r in rows
        ],
    }


@router.get("/metrics")
def sinks_metrics(user: User = Depends(_require_admin)) -> dict:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    rows = metrics().list_org(user.org_id)
    return {
        "org_id": str(user.org_id),
        "items": [
            {
                "sink": r["sink"],
                "samples": r["samples"],
                "success_count": r["success_count"],
                "error_count": r["error_count"],
                "success_rate": r["success_rate"],
                "p50_latency_ms": r["p50_latency_ms"],
                "p95_latency_ms": r["p95_latency_ms"],
            }
            for r in rows
        ],
    }
