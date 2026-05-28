/**
 * Memories layout route. Renders a top tab nav (My / Shared / Settings) and
 * an <Outlet /> for the sub-routes. Visiting `/memories` redirects to the
 * "My memories" page so the legacy entry point keeps working.
 */
import { Link, Outlet, createFileRoute, redirect, useRouterState } from '@tanstack/react-router'

export const Route = createFileRoute('/memories')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/memories') throw redirect({ to: '/memories/my' })
  },
  component: MemoriesLayout,
})

type Tab = {
  to: '/memories/my' | '/memories/shared' | '/memories/settings'
  label: string
  testId: string
}

const TABS: readonly Tab[] = [
  { to: '/memories/my', label: 'My memories', testId: 'mem-tab-my' },
  { to: '/memories/shared', label: 'Shared', testId: 'mem-tab-shared' },
  { to: '/memories/settings', label: 'Settings', testId: 'mem-tab-settings' },
] as const

function MemoriesLayout() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })

  return (
    <div className="main-inner" data-testid="memories-shell" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
      <div className="screen-head" style={{ flexShrink: 0 }}>
        <div>
          <h1>Memories</h1>
          <div className="sub">Long-term context used across conversations</div>
        </div>
      </div>

      <nav
        aria-label="Memories sections"
        style={{
          display: 'flex',
          gap: 4,
          borderBottom: '1px solid var(--line)',
          padding: '0 16px',
          flexShrink: 0,
        }}
      >
        {TABS.map((t) => {
          const active = pathname.startsWith(t.to)
          return (
            <Link
              key={t.to}
              to={t.to}
              data-testid={t.testId}
              style={{
                padding: '8px 12px',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                color: active ? 'var(--ink)' : 'var(--ink-3)',
                borderBottom: `2px solid ${active ? 'var(--ink)' : 'transparent'}`,
                marginBottom: -1,
                textDecoration: 'none',
              }}
            >
              {t.label}
            </Link>
          )
        })}
      </nav>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </div>
    </div>
  )
}
