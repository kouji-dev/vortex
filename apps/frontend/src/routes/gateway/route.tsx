/**
 * Gateway layout route. Chat-style two-pane shell (ModuleShell): white section
 * nav on the left, white ribbon header + content on the right. Sub-routes
 * render inside the <Outlet />.
 */
import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'
import { ModuleShell, type ModuleNavItem } from '~/components/shell/ModuleShell'
import { useMeQuery } from '~/hooks/useMeQuery'
import { isAdminActor } from '~/lib/admin-permissions'

export const Route = createFileRoute('/gateway')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/gateway') throw redirect({ to: '/gateway/overview' })
  },
  component: GatewayLayout,
})

const SECTIONS: readonly ModuleNavItem[] = [
  { to: '/gateway/overview', label: 'Overview', testId: 'gw-nav-overview' },
  { to: '/gateway/providers', label: 'Providers', testId: 'gw-nav-providers' },
  { to: '/gateway/models', label: 'Models', testId: 'gw-nav-models' },
  { to: '/gateway/routing', label: 'Routing', testId: 'gw-nav-routing' },
  { to: '/gateway/guardrails', label: 'Guardrails', testId: 'gw-nav-guardrails' },
  { to: '/gateway/traces', label: 'Traces', testId: 'gw-nav-traces' },
  { to: '/gateway/playground', label: 'Playground', testId: 'gw-nav-playground' },
  { to: '/gateway/evals', label: 'Evals', testId: 'gw-nav-evals' },
  { to: '/gateway/snippets', label: 'Snippets', testId: 'gw-nav-snippets' },
]

function GatewayLayout() {
  const me = useMeQuery()
  const allowed = me.isSuccess && isAdminActor(me.data?.roles)

  if (me.isSuccess && !allowed) return <GatewayForbidden />

  return (
    <ModuleShell
      testId="gateway-shell"
      moduleName="Gateway"
      moduleSub="Unified LLM control plane · providers / routing / limits"
      groups={[{ items: SECTIONS }]}
    >
      {me.isPending ? (
        <div className="panel" style={{ padding: 20, fontSize: 12, color: 'var(--ink-3)' }}>
          Loading…
        </div>
      ) : (
        <Outlet />
      )}
      <GatewayContentStyles />
    </ModuleShell>
  )
}

/** Content-only classes used by Gateway sub-pages (nav/grid now live in ModuleShell). */
function GatewayContentStyles() {
  return (
    <style>{`
      .gw-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
      .gw-kpi { background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
      .gw-kpi-label { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; }
      .gw-kpi-value { font-size: 22px; font-weight: 600; color: var(--ink); margin-top: 4px; }
      .gw-kpi-sub { font-size: 11px; color: var(--ink-3); margin-top: 2px; }
      .gw-badge { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.05em; font-family: var(--font-mono); }
      .gw-badge.ok { background: rgba(0,160,80,0.12); color: var(--green, #2ea36b); }
      .gw-badge.bad { background: rgba(220,60,60,0.12); color: var(--red, #c43c3c); }
      .gw-badge.warn { background: rgba(210,150,30,0.12); color: var(--amber, #c08820); }
      .gw-cap { display: inline-block; font-size: 10px; padding: 1px 5px; border-radius: 3px; background: var(--bg-2); color: var(--ink-2); margin-right: 4px; font-family: var(--font-mono); }
      .gw-input { border-radius: 4px; border: 1px solid var(--line); background: var(--bg); color: var(--ink); padding: 4px 8px; font-size: 12px; }
    `}</style>
  )
}

function GatewayForbidden() {
  return (
    <div className="main-inner" data-testid="gateway-forbidden">
      <div className="panel" style={{ padding: 32, textAlign: 'center' }}>
        <h2 style={{ fontSize: 16, marginBottom: 8 }}>403 — Forbidden</h2>
        <p style={{ fontSize: 13, color: 'var(--ink-3)' }}>Gateway is admin-only.</p>
      </div>
    </div>
  )
}
