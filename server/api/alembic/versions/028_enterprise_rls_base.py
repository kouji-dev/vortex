"""Enterprise RLS base: session-var helpers + bypass mechanism.

Revision ID: 028_enterprise_rls_base
Revises: 027_fix_gemini3_model_ids
Create Date: 2026-04-19

Adds PL/pgSQL helpers used by Row-Level Security policies on enterprise tables:

- ``app.current_org_id()`` — reads ``app.org_id`` session var (set by
  ``middleware/tenant_context.py`` once per request). Returns NULL when unset,
  which makes all RLS-protected rows invisible by default.

- ``app.is_rls_bypassed()`` — reads ``app.bypass_rls`` session var. When set
  to ``'on'`` inside a ``SET LOCAL`` block (see ``core/db/rls.py::bypass_rls``)
  RLS policies let the row through. Used by the retention sweeper, audit worker,
  and other system jobs that legitimately cross tenant boundaries.

Helpers live in the ``app`` schema to keep them off the default search_path
and avoid colliding with user-defined functions.
"""

from __future__ import annotations

from alembic import op

revision = "028_enterprise_rls_base"
down_revision = "027_fix_gemini3_model_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")

    # Non-superuser role used by the app process. Postgres superusers bypass
    # RLS unconditionally, so even FORCE RLS won't protect us if we stay on
    # ``postgres``. Every authenticated request does ``SET LOCAL ROLE app_user``
    # via ``core/db/rls.py::set_org_context`` to drop out of superuser.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                CREATE ROLE app_user NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    # Allow the connecting role (usually ``postgres``) to SET ROLE app_user.
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT app_user TO %I', current_user);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )
    # Grant app_user access to existing + future tables and sequences.
    op.execute("GRANT USAGE ON SCHEMA public, app TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_user")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO app_user")
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_user
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_org_id() RETURNS uuid
        LANGUAGE plpgsql STABLE AS $$
        DECLARE
            v text;
        BEGIN
            v := current_setting('app.org_id', true);
            IF v IS NULL OR v = '' THEN
                RETURN NULL;
            END IF;
            RETURN v::uuid;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.is_rls_bypassed() RETURNS boolean
        LANGUAGE plpgsql STABLE AS $$
        DECLARE
            v text;
        BEGIN
            v := current_setting('app.bypass_rls', true);
            RETURN v = 'on';
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.is_rls_bypassed()")
    op.execute("DROP FUNCTION IF EXISTS app.current_org_id()")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
    # Leave the app_user role in place on downgrade — other environments
    # may still depend on it.
