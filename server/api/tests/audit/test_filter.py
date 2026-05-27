"""AuditFilter dataclass — ensure shape/defaults behave as expected."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ai_portal.audit.protocol import AuditFilter


def test_audit_filter_defaults() -> None:
    f = AuditFilter()
    assert f.org_id is None
    assert f.actor_user_id is None
    assert f.event_type is None
    assert f.limit == 100
    assert f.offset == 0


def test_audit_filter_carries_all_fields() -> None:
    oid = uuid.uuid4()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 6, 1, tzinfo=UTC)
    f = AuditFilter(
        org_id=oid, actor_user_id=42, event_type="org.update",
        resource_type="org", resource_id="x", action="update",
        start=start, end=end, limit=500, offset=10,
    )
    assert f.org_id == oid
    assert f.actor_user_id == 42
    assert f.event_type == "org.update"
    assert f.resource_type == "org"
    assert f.action == "update"
    assert f.start == start and f.end == end
    assert f.limit == 500 and f.offset == 10
