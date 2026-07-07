-- Row-Level Security: hard tenant isolation.
-- Applied after drizzle migrations (idempotent). Run as the DB owner/superuser.
-- The APP connects as a NON-superuser role (vortex_app) so RLS actually applies
-- (superusers bypass RLS). Tenant queries set `app.current_org`; provisioning /
-- platform code sets `app.bypass_rls = on`.

-- ── app role (non-superuser, subject to RLS) ──────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vortex_app') THEN
    CREATE ROLE vortex_app LOGIN PASSWORD 'vortex_app' NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO vortex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vortex_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vortex_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vortex_app;

-- ── tenant isolation policies ─────────────────────────────────
-- Helper predicate: bypass OR row belongs to the current org.
-- current_setting(..., true) → NULL when unset → deny by default.

DO $$
DECLARE
  t text;
  org_col text;
  tenant_tables text[] := ARRAY[
    'organizations','subscriptions','teams','memberships','apps','app_access',
    'api_keys','provider_credentials','usage_records','audit_logs',
    'contracts','usage_rollups','credit_wallets','credit_ledger'
  ];
BEGIN
  FOREACH t IN ARRAY tenant_tables LOOP
    org_col := CASE WHEN t = 'organizations' THEN 'id' ELSE 'org_id' END;
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant', t);
    EXECUTE format($f$
      CREATE POLICY %I ON %I
      USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR %I = current_setting('app.current_org', true)
      )
      WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR %I = current_setting('app.current_org', true)
      )
    $f$, t || '_tenant', t, org_col, org_col);
  END LOOP;
END $$;
