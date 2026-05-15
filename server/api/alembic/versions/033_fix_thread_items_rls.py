# server/api/alembic/versions/033_fix_thread_items_rls.py
"""Fix thread_items RLS policy: use app.current_org_id() function, not literal session var.

Migration 031 created the policy with
``current_setting('app.current_org_id', true)::uuid``, which reads a Postgres
session variable literally named ``app.current_org_id``. The app never sets
that var — ``set_org_context()`` sets ``app.org_id``. The intended source of
truth is the ``app.current_org_id()`` SQL function (defined in migration 028),
which reads ``app.org_id`` and is the form every other RLS-protected table
uses (see migration 029). Result before this fix: every SELECT on
``thread_items`` returned zero rows because ``NULL::uuid = org_id`` is NULL.

Aligns with the pattern in migration 029:
  - USING + WITH CHECK both gated by ``org_id = app.current_org_id() OR app.is_rls_bypassed()``
  - FORCE ROW LEVEL SECURITY so table-owner writes are also constrained
"""

from __future__ import annotations

from alembic import op

revision = "033_fix_thread_items_rls"
down_revision = "032_dev_user_admin_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS thread_items_org_isolation ON thread_items")
    op.execute("ALTER TABLE thread_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY thread_items_org_isolation ON thread_items
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS thread_items_org_isolation ON thread_items")
    op.execute("ALTER TABLE thread_items NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY thread_items_org_isolation ON thread_items "
        "USING (org_id = current_setting('app.current_org_id', true)::uuid)"
    )
