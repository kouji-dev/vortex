/**
 * Admin (Control Plane) layout route. Lists 11 admin sections in a side-nav.
 * Sub-routes render inside the <Outlet />. Page-level 403 enforcement is
 * server-side; this is just a UX guard rail.
 */
import { Link, Outlet, createFileRoute, redirect, useRouterState } from '@tanstack/react-router'
import * as React from 'react'
import { useMeQuery } from '~/hooks/useMeQuery'
import { isAdminActor } from '~/lib/admin-permissions'

export const Route = createFileRoute('/admin')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/admin') throw redirect({ to: '/admin/members' })
  },
  component: AdminLayout,
})

type Section = {
  to: string
  label: string
  enabled: boolean
  testId: string
}

// All admin sections enabled (O1-O10 + SCIM).
const SECTIONS: readonly Section[] = [
  { to: '/admin/members', label: 'Members', enabled: true, testId: 'admin-nav-members' },
  { to: '/admin/teams', label: 'Teams', enabled: true, testId: 'admin-nav-teams' },
  { to: '/admin/sso', label: 'SSO', enabled: true, testId: 'admin-nav-sso' },
  { to: '/admin/directory', label: 'Directory', enabled: true, testId: 'admin-nav-directory' },
  { to: '/admin/scim', label: 'SCIM', enabled: true, testId: 'admin-nav-scim' },
  { to: '/admin/api-keys', label: 'API Keys', enabled: true, testId: 'admin-nav-api-keys' },
  { to: '/admin/audit', label: 'Audit', enabled: true, testId: 'admin-nav-audit' },
  { to: '/admin/usage', label: 'Usage', enabled: true, testId: 'admin-nav-usage' },
  { to: '/admin/budgets', label: 'Budgets', enabled: true, testId: 'admin-nav-budgets' },
  { to: '/admin/webhooks', label: 'Webhooks', enabled: true, testId: 'admin-nav-webhooks' },
  { to: '/admin/billing', label: 'Billing', enabled: true, testId: 'admin-nav-billing' },
  { to: '/admin/settings', label: 'Settings', enabled: true, testId: 'admin-nav-settings' },
  { to: '/admin/data', label: 'Data', enabled: true, testId: 'admin-nav-data' },
  { to: '/admin/memory-policies', label: 'Memory Policies', enabled: true, testId: 'admin-nav-memory-policies' },
  { to: '/admin/memory-analytics', label: 'Memory Analytics', enabled: true, testId: 'admin-nav-memory-analytics' },
] as const

function AdminLayout() {
  const me = useMeQuery()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const allowed = me.isSuccess && isAdminActor(me.data?.roles)

  if (me.isSuccess && !allowed) {
    return <AdminForbidden />
  }

  return (
    <div className="main-inner" data-testid="admin-shell">
      <div className="screen-head">
        <div>
          <h1>Admin</h1>
          <div className="sub">Control Plane · org administration</div>
        </div>
      </div>

      <div className="admin-grid">
        <nav className="admin-side" aria-label="Admin sections">
          {SECTIONS.map((s) => {
            const active = pathname.startsWith(s.to)
            const cls = `admin-nav-item${active ? ' active' : ''}${s.enabled ? '' : ' disabled'}`
            if (!s.enabled) {
              return (
                <span key={s.to} className={cls} data-testid={s.testId} aria-disabled="true">
                  {s.label}
                  <span className="admin-nav-badge">soon</span>
                </span>
              )
            }
            return (
              <Link key={s.to} to={s.to} className={cls} data-testid={s.testId}>
                {s.label}
              </Link>
            )
          })}
        </nav>

        <div className="admin-body">
          {me.isPending ? (
            <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }}>
              Loading…
            </div>
          ) : (
            <Outlet />
          )}
        </div>
      </div>

      <AdminInlineStyles />
    </div>
  )
}

function AdminForbidden() {
  return (
    <div className="main-inner" data-testid="admin-forbidden">
      <div className="panel" style={{ padding: 32, textAlign: 'center' }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>403 — Forbidden</h2>
        <p style={{ fontSize: 13, color: 'var(--ink-3)' }}>
          You don&apos;t have permission to view Admin. Ask an org owner for the admin role.
        </p>
      </div>
    </div>
  )
}

/**
 * Local styles — kept inline so this slice doesn't have to touch app.css.
 * Once stable these should be moved into the @layer components block.
 */
function AdminInlineStyles() {
  return (
    <style>{`
      .admin-grid {
        display: grid;
        grid-template-columns: 200px 1fr;
        gap: 16px;
        align-items: start;
      }
      .admin-side {
        display: flex;
        flex-direction: column;
        gap: 2px;
        position: sticky;
        top: 16px;
      }
      .admin-nav-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 12px;
        color: var(--ink-2);
        text-decoration: none;
        font-family: var(--font-mono);
      }
      .admin-nav-item:hover { background: var(--bg-2); color: var(--ink); }
      .admin-nav-item.active { background: var(--bg-2); color: var(--ink); font-weight: 600; }
      .admin-nav-item.disabled { color: var(--ink-3); cursor: not-allowed; }
      .admin-nav-item.disabled:hover { background: transparent; }
      .admin-nav-badge {
        font-size: 9px;
        padding: 1px 5px;
        border-radius: 3px;
        background: var(--bg-2);
        color: var(--ink-3);
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
    `}</style>
  )
}
