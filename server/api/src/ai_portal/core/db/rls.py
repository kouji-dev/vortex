"""Row-Level Security helpers.

Every request that touches RLS-protected tables (``thread_items``,
``audit_events``, ``rbac_policy``, ``usage_quota``, ``retention_policy``,
``usage_rollup``) must have ``app.org_id`` set on its DB session. The
tenant-context middleware (``middleware/tenant_context.py``) handles this for
normal HTTP traffic; background workers and the sweeper use
``set_org_context`` / ``bypass_rls`` directly.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session


def set_org_context(db: Session, org_id: uuid.UUID | str | None) -> None:
    """Bind ``app.org_id`` and drop to the ``app_user`` role.

    Postgres superusers bypass RLS unconditionally (FORCE RLS does not help).
    The app typically connects as ``postgres`` in dev/selfhosted, so every
    authenticated request switches to ``app_user`` (non-superuser, no
    BYPASSRLS) for the duration of the transaction.

    ``SET LOCAL`` only applies inside an active transaction. The ORM opens
    one implicitly on first query, so call this once the request's user is
    known but before any data access, or inside the worker's own transaction.
    """
    db.execute(text("SET LOCAL ROLE app_user"))
    if org_id is None:
        db.execute(text("SET LOCAL app.org_id = ''"))
        return
    # SET LOCAL does not accept bound parameters — inline the UUID (hex+hyphens only, safe).
    db.execute(text(f"SET LOCAL app.org_id = '{str(org_id)}'"))


@contextmanager
def bypass_rls(db: Session) -> Iterator[None]:
    """Let system jobs cross tenant boundaries for the duration of the block.

    Scoped via ``SET LOCAL`` so it cannot leak out of the enclosing
    transaction. Used by:
      - the retention sweeper (deletes across orgs)
      - the audit worker (writes on behalf of every org)
      - the usage aggregator (rolls up across orgs)

    Sets ``app.bypass_rls`` — the RLS policy expression treats that as
    permission to return every row. The ``app_user`` role is preserved so
    the audit-events immutability trigger still fires (UPDATE/DELETE are
    allowed only when bypass is on).
    """
    db.execute(text("SET LOCAL app.bypass_rls = 'on'"))
    try:
        yield
    finally:
        db.execute(text("SET LOCAL app.bypass_rls = 'off'"))
