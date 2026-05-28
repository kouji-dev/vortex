import { Link, useRouterState } from '@tanstack/react-router'
import { BarChart2, Bot, Brain, ChevronUp, Database, Library, LogOut, MessageSquare, Router as RouterIcon, Shield } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { useConversationsListQuery } from '~/hooks/useConversationsListQuery'
import { useMeQuery } from '~/hooks/useMeQuery'
import { isAdminActor } from '~/lib/admin-permissions'

const LANDING_URL = import.meta.env.VITE_LANDING_URL ?? '/'

type NavItem = {
  to: string
  Icon: LucideIcon
  label: string
  testId: string
  adminOnly?: boolean
  group?: 'workspace' | 'modules' | 'admin'
}

const NAV: readonly NavItem[] = [
  // Workspace
  { to: '/chat/conversations', Icon: MessageSquare, label: 'Chat', testId: 'nav-chat', group: 'workspace' },
  { to: '/knowledge-bases', Icon: Library, label: 'Knowledge', testId: 'nav-knowledge', group: 'workspace' },
  { to: '/memories', Icon: Brain, label: 'Memories', testId: 'nav-memories', group: 'workspace' },
  { to: '/org/consumption', Icon: BarChart2, label: 'Consumption', testId: 'nav-consumption', group: 'workspace' },
  // Modules
  { to: '/gateway/overview', Icon: RouterIcon, label: 'Gateway', testId: 'nav-gateway', group: 'modules', adminOnly: true },
  { to: '/rag/kbs', Icon: Database, label: 'RAG', testId: 'nav-rag', group: 'modules', adminOnly: true },
  { to: '/workers', Icon: Bot, label: 'Workers', testId: 'nav-workers', group: 'modules', adminOnly: true },
  // Admin
  { to: '/admin', Icon: Shield, label: 'Admin', testId: 'nav-admin', group: 'admin', adminOnly: true },
] as const

const GROUPS: { id: 'workspace' | 'modules' | 'admin'; label: string }[] = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'modules', label: 'Modules' },
  { id: 'admin', label: 'Admin' },
]

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
  const [menuOpen, setMenuOpen] = React.useState(false)
  const menuRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!menuOpen) return
    function onClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [menuOpen])

  const user = me.data
  const convList = conversations.data ?? []
  const isOnChat = path.startsWith('/chat')
  const isAdmin = isAdminActor(user?.roles)

  return (
    <aside
      className="sidebar hidden md:flex"
      aria-label="Main navigation"
      data-testid="app-sidebar"
    >
      {/* Primary nav grouped by section */}
      {GROUPS.map((group) => {
        const items = NAV.filter((n) => n.group === group.id && (!n.adminOnly || isAdmin))
        if (items.length === 0) return null
        return (
          <nav key={group.id} className="side-section" aria-label={group.label}>
            <div className="side-label">{group.label}</div>
            {items.map(({ to, Icon, label, testId }) => {
              const active =
                to === '/chat/conversations'
                  ? path.startsWith('/chat')
                  : to === '/gateway/overview'
                    ? path.startsWith('/gateway')
                    : path.startsWith(to)
              return (
                <Link
                  key={to}
                  to={to}
                  className={`side-item${active ? ' active' : ''}`}
                  data-testid={testId}
                >
                  <Icon className="side-icon" strokeWidth={2} aria-hidden />
                  <span>{label}</span>
                </Link>
              )
            })}
          </nav>
        )
      })}

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

      {/* Footer org card with avatar dropdown */}
      <div className="sidebar-foot">
        <div className="relative" ref={menuRef}>
          {menuOpen && (
            <div className="avatar-menu">
              <a
                href={LANDING_URL}
                className="avatar-menu-item"
                onClick={() => setMenuOpen(false)}
              >
                <LogOut className="size-3.5 shrink-0" aria-hidden />
                Log out
              </a>
            </div>
          )}
          <button
            className="org-card w-full text-left"
            onClick={() => setMenuOpen((o) => !o)}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
          >
            <div className="avatar" aria-hidden>
              {initials(user?.display_name, user?.email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="name truncate">{user?.display_name ?? user?.email ?? 'Loading…'}</div>
              <div className="meta mono">{user?.roles?.[0] ?? ''}</div>
            </div>
            <ChevronUp
              className={`size-3.5 shrink-0 text-ink-3 transition-transform ${menuOpen ? '' : 'rotate-180'}`}
              aria-hidden
            />
          </button>
        </div>
      </div>
    </aside>
  )
}
