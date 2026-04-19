"""Tenant-context glue for request-scoped RLS.

FastAPI middleware proper cannot touch the request-scoped DB session
(dependencies haven't run yet, the session doesn't exist). So tenant context
is bound in two places:

1. ``auth/deps.py::get_current_user`` calls ``set_org_context`` on the
   shared request session once the user is authenticated. Every protected
   route inherits this because it depends (directly or transitively) on
   ``get_current_user``.

2. Background workers call ``set_org_context`` (or ``bypass_rls``) on the
   session they just opened before issuing any query.

This module re-exports the helpers and provides a FastAPI dependency
``tenant_scoped_db`` for routes that want an explicit, typed handle on
the tenant-bound session.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.core.db.rls import bypass_rls, set_org_context

__all__ = ["bypass_rls", "set_org_context", "tenant_scoped_db"]


def tenant_scoped_db(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Session:
    """DB session with ``app.org_id`` pre-set for the caller's org."""
    set_org_context(db, user.org_id)
    return db
