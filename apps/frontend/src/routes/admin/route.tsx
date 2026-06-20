/**
 * Admin (Control Plane) layout route. Chat-style two-pane shell (ModuleShell):
 * white section nav on the left, white ribbon header + content on the right.
 * Page-level 403 enforcement is server-side; this is just a UX guard rail.
 */
import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'
import { ModuleShell, type ModuleNavItem } from '~/components/shell/ModuleShell'
import { useMeQuery } from '~/hooks/useMeQuery'
import { isAdminActor } from '~/lib/admin-permissions'

export const Route = createFileRoute('/admin')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/admin') throw redirect({ to: '/admin/members' })
  },
  component: AdminLayout,
})

// All admin sections enabled (O1-O10 + SCIM).
const SECTIONS: readonly ModuleNavItem[] = [
  { to: '/admin/members', label: 'Members', testId: 'admin-nav-members' },
  { to: '/admin/teams', label: 'Teams', testId: 'admin-nav-teams' },
  { to: '/admin/sso', label: 'SSO', testId: 'admin-nav-sso' },
  { to: '/admin/directory', label: 'Directory', testId: 'admin-nav-directory' },
  { to: '/admin/scim', label: 'SCIM', testId: 'admin-nav-scim' },
  { to: '/admin/api-keys', label: 'API Keys', testId: 'admin-nav-api-keys' },
  { to: '/admin/audit', label: 'Audit', testId: 'admin-nav-audit' },
  { to: '/admin/usage', label: 'Usage', testId: 'admin-nav-usage' },
  { to: '/admin/budgets', label: 'Budgets', testId: 'admin-nav-budgets' },
  { to: '/admin/webhooks', label: 'Webhooks', testId: 'admin-nav-webhooks' },
  { to: '/admin/billing', label: 'Billing', testId: 'admin-nav-billing' },
  { to: '/admin/settings', label: 'Settings', testId: 'admin-nav-settings' },
  { to: '/admin/data', label: 'Data', testId: 'admin-nav-data' },
  { to: '/admin/memory-policies', label: 'Memory Policies', testId: 'admin-nav-memory-policies' },
  { to: '/admin/memory-analytics', label: 'Memory Analytics', testId: 'admin-nav-memory-analytics' },
]

function AdminLayout() {
  const me = useMeQuery()
  const allowed = me.isSuccess && isAdminActor(me.data?.roles)

  if (me.isSuccess && !allowed) return <AdminForbidden />

  return (
    <ModuleShell
      testId="admin-shell"
      moduleName="Admin"
      moduleSub="Control Plane · org administration"
      groups={[{ items: SECTIONS }]}
    >
      {me.isPending ? (
        <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }}>
          Loading…
        </div>
      ) : (
        <Outlet />
      )}
    </ModuleShell>
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
