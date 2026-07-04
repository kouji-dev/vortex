-- Runs once on first container init (docker-entrypoint-initdb.d), as the
-- superuser. Creates the NON-superuser role the app connects as at runtime so
-- Postgres RLS actually applies (superusers bypass RLS). Table grants land here
-- via ALTER DEFAULT PRIVILEGES for tables the migrations create later; the RLS
-- migration re-grants + defines policies (and also runs this idempotently for
-- managed Postgres that has no init hooks, e.g. Render).

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
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO vortex_app;
