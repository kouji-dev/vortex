/**
 * Workers layout route. Chat-style two-pane shell (ModuleShell). Admin-only.
 * Sub-routes render inside the <Outlet />.
 */
import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'
import { ModuleShell, type ModuleNavItem } from '~/components/shell/ModuleShell'
import { useMeQuery } from '~/hooks/useMeQuery'
import { isAdminActor } from '~/lib/admin-permissions'

export const Route = createFileRoute('/workers')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/workers') throw redirect({ to: '/workers/instances' })
  },
  component: WorkersLayout,
})

const SECTIONS: readonly ModuleNavItem[] = [
  { to: '/workers/instances', label: 'Workers', testId: 'wk-nav-instances' },
  { to: '/workers/tasks', label: 'Tasks', testId: 'wk-nav-tasks' },
  { to: '/workers/pools', label: 'Pools', testId: 'wk-nav-pools' },
  { to: '/workers/integrations', label: 'Integrations', testId: 'wk-nav-integrations' },
  { to: '/workers/settings', label: 'Settings', testId: 'wk-nav-settings' },
  { to: '/workers/analytics', label: 'Analytics', testId: 'wk-nav-analytics' },
]

function WorkersLayout() {
  const me = useMeQuery()
  const allowed = me.isSuccess && isAdminActor(me.data?.roles)

  if (me.isSuccess && !allowed) return <WorkersForbidden />

  return (
    <ModuleShell
      testId="workers-shell"
      moduleName="Workers"
      moduleSub="Autonomous coding agents · tasks / pools / approvals"
      groups={[{ items: SECTIONS }]}
    >
      {me.isPending ? (
        <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }}>
          Loading…
        </div>
      ) : (
        <Outlet />
      )}
      <WorkersContentStyles />
    </ModuleShell>
  )
}

function WorkersForbidden() {
  return (
    <div className="main-inner" data-testid="workers-forbidden">
      <div className="panel" style={{ padding: 32, textAlign: 'center' }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>403 — Forbidden</h2>
        <p style={{ fontSize: 13, color: 'var(--ink-3)' }}>Workers is admin-only.</p>
      </div>
    </div>
  )
}

/** Content-only classes used by Workers sub-pages (nav/grid now live in ModuleShell). */
function WorkersContentStyles() {
  return (
    <style>{`
      .wk-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
      .wk-card { background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
      .wk-card-label { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; }
      .wk-card-value { font-size: 22px; font-weight: 600; color: var(--ink); margin-top: 4px; }
      .wk-pane { background: var(--bg); border: 1px solid var(--line); border-radius: 6px; }
      .wk-pane-head { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--line); font-size: 11px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; }
      .wk-pane-body { padding: 10px 12px; font-size: 12px; }
      .wk-event-row { display: grid; grid-template-columns: 60px 90px 1fr; gap: 8px; padding: 4px 0; font-family: var(--font-mono); font-size: 11px; border-bottom: 1px dashed var(--line); }
      .wk-event-row:last-child { border-bottom: none; }
      .wk-event-ts { color: var(--ink-3); }
      .wk-event-kind { color: var(--ink-2); font-weight: 600; }
      .wk-event-payload { color: var(--ink); white-space: pre-wrap; word-break: break-word; }
      .wk-term { background: #0b0b0b; color: #d8d8d8; font-family: var(--font-mono); font-size: 11px; padding: 10px; border-radius: 4px; max-height: 360px; overflow: auto; white-space: pre-wrap; }
      .wk-detail-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; }
      .wk-input { border-radius: 4px; border: 1px solid var(--line); background: var(--bg); color: var(--ink); padding: 4px 8px; font-size: 12px; }
    `}</style>
  )
}
