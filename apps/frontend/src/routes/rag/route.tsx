/**
 * RAG layout — sidebar with the 12 sub-pages.
 *
 * Pages split between global (list / marketplace / search providers) and
 * per-KB (overview / documents / connectors / settings / permissions /
 * playground / analytics / evals / quarantine). When no KB is selected,
 * per-KB nav items disable and tell the user to pick a KB from the list.
 */
import { Link, Outlet, createFileRoute, redirect, useRouterState } from '@tanstack/react-router'

export const Route = createFileRoute('/rag')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/rag') throw redirect({ to: '/rag/kbs' })
  },
  component: RagLayout,
})

type Section = { to: string; label: string }

const GLOBAL: readonly Section[] = [
  { to: '/rag/kbs', label: 'Knowledge bases' },
  { to: '/rag/marketplace', label: 'Connector marketplace' },
  { to: '/rag/search-providers', label: 'Search providers' },
]

const PER_KB: readonly Section[] = [
  { to: 'overview', label: 'Overview' },
  { to: 'documents', label: 'Documents' },
  { to: 'connectors', label: 'Connectors' },
  { to: 'settings', label: 'Settings' },
  { to: 'permissions', label: 'Permissions' },
  { to: 'playground', label: 'Playground' },
  { to: 'analytics', label: 'Analytics' },
  { to: 'evals', label: 'Evals' },
  { to: 'quarantine', label: 'Quarantine' },
]

const KB_ROUTE = /^\/rag\/kbs\/(\d+)/

function RagLayout() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const match = KB_ROUTE.exec(pathname)
  const kbId = match ? match[1] : null

  return (
    <div className="main-inner" data-testid="rag-shell">
      <div className="screen-head">
        <div>
          <h1>Knowledge bases</h1>
          <div className="sub">RAG · documents · connectors · evals · analytics</div>
        </div>
      </div>

      <div className="rag-grid">
        <nav className="rag-side" aria-label="RAG sections">
          <div className="rag-nav-group">Global</div>
          {GLOBAL.map((s) => (
            <Link
              key={s.to}
              to={s.to}
              className={`rag-nav-item${pathname.startsWith(s.to) ? ' active' : ''}`}
              data-testid={`rag-nav-${s.to.split('/').pop()}`}
            >
              {s.label}
            </Link>
          ))}
          {kbId && (
            <>
              <div className="rag-nav-group" style={{ marginTop: 12 }}>
                KB {kbId}
              </div>
              {PER_KB.map((s) => {
                const target = `/rag/kbs/${kbId}/${s.to}`
                const active = pathname === target || pathname.startsWith(`${target}/`)
                return (
                  <Link
                    key={s.to}
                    to={target}
                    className={`rag-nav-item${active ? ' active' : ''}`}
                    data-testid={`rag-nav-${s.to}`}
                  >
                    {s.label}
                  </Link>
                )
              })}
            </>
          )}
        </nav>

        <div className="rag-body">
          <Outlet />
        </div>
      </div>

      <RagInlineStyles />
    </div>
  )
}

function RagInlineStyles() {
  return (
    <style>{`
      .rag-grid {
        display: grid;
        grid-template-columns: 220px 1fr;
        gap: 16px;
        align-items: start;
      }
      .rag-side {
        display: flex;
        flex-direction: column;
        gap: 2px;
        position: sticky;
        top: 16px;
      }
      .rag-nav-group {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--ink-3);
        padding: 4px 10px;
      }
      .rag-nav-item {
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
      .rag-nav-item:hover { background: var(--bg-2); color: var(--ink); }
      .rag-nav-item.active { background: var(--bg-2); color: var(--ink); font-weight: 600; }
      .rag-kpi-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
      }
      .rag-kpi {
        background: var(--bg);
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 12px 14px;
      }
      .rag-kpi-label { font-size: 10px; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; }
      .rag-kpi-value { font-size: 22px; font-weight: 600; color: var(--ink); margin-top: 4px; }
      .rag-kpi-sub { font-size: 11px; color: var(--ink-3); margin-top: 2px; }
      .rag-tile-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 10px;
      }
      .rag-tile {
        background: var(--bg);
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 12px;
        cursor: pointer;
      }
      .rag-tile:hover { border-color: var(--ink-3); }
      .rag-tile h4 { font-size: 13px; margin: 0 0 4px; }
      .rag-tile p { font-size: 11px; color: var(--ink-3); margin: 0; }
      .rag-cat {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--ink-3);
        margin: 12px 0 6px;
      }
      .rag-input, .rag-textarea {
        border-radius: 4px;
        border: 1px solid var(--line);
        background: var(--bg);
        color: var(--ink);
        padding: 4px 8px;
        font-size: 12px;
        width: 100%;
        box-sizing: border-box;
      }
      .rag-textarea { font-family: var(--font-mono); resize: vertical; }
      .rag-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .rag-table th, .rag-table td {
        text-align: left;
        border-bottom: 1px solid var(--line);
        padding: 6px 8px;
      }
      .rag-table th { font-size: 10px; text-transform: uppercase; color: var(--ink-3); }
      .rag-badge {
        display: inline-block;
        font-size: 10px;
        padding: 1px 6px;
        border-radius: 3px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-family: var(--font-mono);
      }
      .rag-badge.ok { background: rgba(0,160,80,0.12); color: var(--green, #2ea36b); }
      .rag-badge.bad { background: rgba(220,60,60,0.12); color: var(--red, #c43c3c); }
      .rag-badge.warn { background: rgba(210,150,30,0.12); color: var(--amber, #c08820); }
    `}</style>
  )
}
