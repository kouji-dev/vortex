import { Link, useRouterState } from '@tanstack/react-router'

import { useConversationsListQuery } from '~/hooks/useConversationsListQuery'
import { useMeQuery } from '~/hooks/useMeQuery'

const NAV = [
  { to: '/chat/conversations', n: '01', label: 'Chat', testId: 'nav-chat' },
  { to: '/knowledge-bases', n: '02', label: 'Knowledge', testId: 'nav-knowledge' },
  { to: '/memories', n: '03', label: 'Memories', testId: 'nav-memories' },
  { to: '/org/settings', n: '04', label: 'Org Settings', testId: 'nav-org-settings' },
] as const

function relativeTime(iso?: string | null): string {
  if (!iso) return ''
  const d = (Date.now() - new Date(iso).getTime()) / 60000
  if (d < 60) return `${Math.max(1, Math.round(d))}m`
  if (d < 60 * 24) return `${Math.round(d / 60)}h`
  return `${Math.round(d / (60 * 24))}d`
}

/** Returns up to 2 initials from a display name or email. */
function initials(name?: string | null, email?: string): string {
  const n = name?.trim()
  if (n) {
    const parts = n.split(/\s+/).filter(Boolean)
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    return n.slice(0, 2).toUpperCase()
  }
  if (email) return email.slice(0, 2).toUpperCase()
  return '?'
}

export function AppSidebar() {
  const path = useRouterState({ select: (s) => s.location.pathname })
  const conversations = useConversationsListQuery()
  const me = useMeQuery()

  const user = me.data
  const convList = conversations.data ?? []
  const isOnChat = path.startsWith('/chat')

  return (
    <aside
      className="sidebar hidden md:flex"
      aria-label="Main navigation"
      data-testid="app-sidebar"
    >
      {/* Primary nav */}
      <nav className="side-section" aria-label="Primary">
        <div className="side-label">Workspace</div>
        {NAV.map(({ to, n, label, testId }) => {
          // Match /chat/conversations when on any /chat sub-route
          const active =
            to === '/chat/conversations'
              ? path.startsWith('/chat')
              : path.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              className={`side-item${active ? ' active' : ''}`}
              data-testid={testId}
            >
              <span className="side-icon mono">{n}</span>
              <span>{label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Inline conversation list (visible when on Chat routes) */}
      {isOnChat && (
        <div className="side-section-convs" aria-label="Recent conversations">
          <div className="side-label-row">
            <span className="side-label">Recent</span>
            <Link to="/chat/conversations" className="btn btn-xs">
              New
            </Link>
          </div>
          {convList.length === 0 && !conversations.isPending && (
            <div className="conv-mini-label">No conversations yet</div>
          )}
          {convList.slice(0, 12).map((c) => {
            const active = path.endsWith(String(c.id))
            return (
              <Link
                key={c.id}
                to="/chat/conversations/$id"
                params={{ id: String(c.id) }}
                className={`conv-mini${active ? ' active' : ''}`}
              >
                <span className="title">{c.title ?? 'Untitled'}</span>
                <span className="meta mono">{relativeTime(c.created_at)}</span>
              </Link>
            )
          })}
        </div>
      )}

      {/* Footer org card */}
      <div className="sidebar-foot">
        <div className="org-card">
          <div className="avatar" aria-hidden>
            {initials(user?.display_name, user?.email)}
          </div>
          <div>
            <div className="name">{user?.display_name ?? user?.email ?? 'Loading…'}</div>
            <div className="meta mono">{user?.roles?.[0] ?? ''}</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
