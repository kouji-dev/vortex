"""TeamService — CRUD, membership, per-team key count + usage aggregation.

Postgres-gated (mirrors tests/api_keys). Keys stay user-owned; per-team counts
derive through team_members → api_keys.actor_user_id.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

# Ensure referenced tables load before flush.
import ai_portal.auth.model  # noqa: F401
import ai_portal.api_keys.model  # noqa: F401
import ai_portal.control_plane.teams.model  # noqa: F401
import ai_portal.usage.model  # noqa: F401

from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'TeamOrg') ON CONFLICT DO NOTHING"),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


def _mk_user(db, org_id: uuid.UUID, email_prefix: str) -> int:
    res = db.execute(
        text(
            "INSERT INTO users (uuid, email, org_id, role, is_active, is_verified) "
            "VALUES (:u, :email, :org, 'member', true, true) RETURNING id"
        ),
        {
            "u": str(uuid.uuid4()),
            "email": f"{email_prefix}-{uuid.uuid4().hex[:8]}@acme.com",
            "org": str(org_id),
        },
    )
    return int(res.scalar_one())


@requires_postgres
def test_create_add_members_and_counts():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.control_plane.teams.service import TeamService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "team-svc")
            u1 = _mk_user(db, org_id, "u1")
            u2 = _mk_user(db, org_id, "u2")
            db.commit()

            svc = TeamService(db)
            team = svc.create(org_id=org_id, slug="eng", name="Engineering")
            assert team.id is not None

            svc.add_member(org_id=org_id, team_id=team.id, user_id=u1, role="lead")
            svc.add_member(org_id=org_id, team_id=team.id, user_id=u2)
            assert svc.member_count(team.id) == 2

            # Per-team key count: u1 owns 2 keys, u2 owns 1 → 3 total.
            keys = ApiKeyService(db)
            keys.create(org_id=org_id, name="k1", actor_user_id=u1)
            keys.create(org_id=org_id, name="k2", actor_user_id=u1)
            keys.create(org_id=org_id, name="k3", actor_user_id=u2)
            assert svc.key_count(org_id=org_id, team_id=team.id) == 3

            # Removing a member drops attribution; keys untouched.
            svc.remove_member(org_id=org_id, team_id=team.id, user_id=u2)
            assert svc.member_count(team.id) == 1
            # u2's key still counted only if still a member — now excluded.
            assert svc.key_count(org_id=org_id, team_id=team.id) == 2
            # But the key row itself still exists for u2.
            remaining = keys.list_for_org(org_id)
            assert len(remaining) == 3
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_usage_aggregates_across_members():
    from ai_portal.control_plane.teams.service import TeamService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "team-usage")
            u1 = _mk_user(db, org_id, "uu1")
            u2 = _mk_user(db, org_id, "uu2")
            db.commit()

            svc = TeamService(db)
            team = svc.create(org_id=org_id, slug="data", name="Data")
            svc.add_member(org_id=org_id, team_id=team.id, user_id=u1)
            svc.add_member(org_id=org_id, team_id=team.id, user_id=u2)

            # Seed usage_rollup rows for both members.
            for uid, tokens, cost in ((u1, 100, "1.50"), (u2, 200, "2.50")):
                db.execute(
                    text(
                        "INSERT INTO usage_rollup "
                        "(org_id, user_id, period_start, period_grain, "
                        " input_tokens, output_tokens, cached_input_tokens, "
                        " cost_usd, message_count) "
                        "VALUES (:org, :uid, now(), 'day', :tin, 10, 0, :cost, 1)"
                    ),
                    {"org": str(org_id), "uid": uid, "tin": tokens, "cost": cost},
                )
            db.commit()

            agg = svc.usage(org_id=org_id, team_id=team.id)
            assert agg["member_count"] == 2
            assert agg["input_tokens"] == 300
            assert agg["output_tokens"] == 20
            assert abs(agg["cost_usd"] - 4.0) < 1e-6
            assert agg["message_count"] == 2
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_slug_unique_per_org_and_user_must_be_in_org():
    from ai_portal.control_plane.teams.service import (
        TeamService,
        TeamSlugTaken,
        UserNotInOrg,
    )
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_a = _mk_org(db, "team-a")
            org_b = _mk_org(db, "team-b")
            outsider = _mk_user(db, org_b, "outsider")
            db.commit()

            svc = TeamService(db)
            svc.create(org_id=org_a, slug="ops", name="Ops")
            try:
                svc.create(org_id=org_a, slug="ops", name="Dup")
                assert False, "expected TeamSlugTaken"
            except TeamSlugTaken:
                db.rollback()

            # Same slug allowed in a different org.
            t_b = svc.create(org_id=org_b, slug="ops", name="Ops B")
            try:
                svc.add_member(org_id=org_b, team_id=t_b.id, user_id=10**9)
                assert False, "expected UserNotInOrg"
            except UserNotInOrg:
                db.rollback()
            db.commit()
    finally:
        db.rollback()
        db.close()
