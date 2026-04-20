// frontend/src/components/layout/BottomTabBar.tsx
import { Link, useLocation } from '@tanstack/react-router'
import {
  Brain,
  LayoutDashboard,
  Library,
  MessageSquare,
} from 'lucide-react'
const TABS = [
  { to: '/', icon: LayoutDashboard, label: 'Home', exact: true },
  { to: '/chat/conversations', icon: MessageSquare, label: 'Chat', exact: false },
  { to: '/knowledge-bases', icon: Library, label: 'KBs', exact: false },
  { to: '/memories', icon: Brain, label: 'Memories', exact: false },
] as const

export function BottomTabBar() {
  const location = useLocation()

  return (
    <nav
      className="flex shrink-0 items-stretch border-t border-line bg-panel"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      aria-label="Main navigation"
    >
      {TABS.map(({ to, icon: Icon, label, exact }) => {
        const active = exact
          ? location.pathname === to
          : location.pathname.startsWith(to)
        return (
          <Link
            key={to}
            to={to}
            className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-ink-3"
          >
            <Icon
              className={`size-5 shrink-0 ${active ? 'text-ink' : ''}`}
              aria-hidden
            />
            <span className={`text-[10px] mono ${active ? 'font-semibold text-ink' : ''}`}>
              {label}
            </span>
          </Link>
        )
      })}
    </nav>
  )
}
