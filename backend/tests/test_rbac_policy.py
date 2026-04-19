"""RBAC evaluator — policy decisions for model/capability/tool."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from tests.conftest import requires_postgres


def _make_user(role: str = "member") -> MagicMock:
    u = MagicMock()
    u.role = role
    u.org_id = uuid.uuid4()
    return u


@requires_postgres
def test_rbac_no_policy_defaults_allow():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.evaluator import evaluate

    db = SessionLocal()
    try:
        user = _make_user("member")
        # No policy row for this random org → default allow.
        decision = evaluate(
            db,
            user=user,
            org_id=uuid.uuid4(),
            resource_type="model",
            resource_key="gpt-4o",
        )
        assert decision.allowed
    finally:
        db.close()


@requires_postgres
def test_rbac_model_allowlist_blocks_unlisted_model():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.evaluator import evaluate
    from ai_portal.rbac.model import RbacPolicy

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(RbacPolicy(
                org_id=org_id,
                model_allowlist=["gpt-4o"],
                default_policy="allow",
            ))
            db.commit()

        user = _make_user("admin")
        decision = evaluate(db, user=user, org_id=org_id, resource_type="model", resource_key="claude-3-5-sonnet-20241022")
        assert not decision.allowed
        assert "allowlist" in decision.reason

        # Listed model is allowed.
        decision2 = evaluate(db, user=user, org_id=org_id, resource_type="model", resource_key="gpt-4o")
        assert decision2.allowed

    finally:
        db.close()


@requires_postgres
def test_rbac_capability_role_binding():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.evaluator import evaluate
    from ai_portal.rbac.model import RbacPolicy

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(RbacPolicy(
                org_id=org_id,
                capability_role_bindings={"reflection": ["admin", "owner"]},
                default_policy="allow",
            ))
            db.commit()

        member = _make_user("member")
        admin = _make_user("admin")

        assert not evaluate(db, user=member, org_id=org_id, resource_type="capability", resource_key="reflection").allowed
        assert evaluate(db, user=admin, org_id=org_id, resource_type="capability", resource_key="reflection").allowed
        # research has no binding → allowed for all
        assert evaluate(db, user=member, org_id=org_id, resource_type="capability", resource_key="research").allowed

    finally:
        db.close()


@requires_postgres
def test_rbac_default_deny():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.rbac.evaluator import evaluate
    from ai_portal.rbac.model import RbacPolicy

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.add(RbacPolicy(org_id=org_id, default_policy="deny"))
            db.commit()

        user = _make_user("member")
        decision = evaluate(db, user=user, org_id=org_id, resource_type="tool", resource_key="web_search")
        assert not decision.allowed
        assert "deny" in decision.reason

    finally:
        db.close()
