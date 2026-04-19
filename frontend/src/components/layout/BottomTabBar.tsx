// frontend/src/components/layout/BottomTabBar.tsx
import { Link, useLocation } from '@tanstack/react-router'
import {
  Brain,
  LayoutDashboard,
  Library,
  MessageSquare,
  MoreHorizontal,
  Settings,
} from 'lucide-react'
import * as React from 'react'

const TABS = [
  { to: '/', icon: LayoutDashboard, label: 'Home', exact: true },
  { to: '/chat/conversations', icon: MessageSquare, label: 'Chat', exact: false },
  { to: '/knowledge-bases', icon: Library, label: 'KBs', exact: false },
  { to: '/memories', icon: Brain, label: 'Memories', exact: false },
] as const

const OVERFLOW_ITEMS = [
  { to: '/org/settings', icon: Settings, label: 'Org Settings' },
] as const

export function BottomTabBar() {
  const location = useLocation()
  const [moreOpen, setMoreOpen] = React.useState(false)

  const isOverflowActive = OVERFLOW_ITEMS.some((item) =>
    location.pathname.startsWith(item.to),
  )

  return (
    <>
      {/* More sheet backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-200 ${moreOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        onClick={() => setMoreOpen(false)}
        aria-hidden
      />

      {/* More sheet */}
      <div
        className={`fixed bottom-0 inset-x-0 z-50 rounded-t-2xl border-t border-line bg-panel transition-transform duration-200 ease-out ${moreOpen ? 'translate-y-0' : 'translate-y-full'}`}
        aria-hidden={!moreOpen}
      >
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line" />
        <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wide text-ink-3 mono">
          More
        </p>
        {OVERFLOW_ITEMS.map(({ to, icon: Icon, label }) => (
          <Link
            key={to}
            to={to}
            onClick={() => setMoreOpen(false)}
            className="flex items-center gap-3 px-4 py-3 text-sm text-ink hover:bg-bg-2"
          >
            <Icon className="size-5 shrink-0 text-ink-3" aria-hidden />
            {label}
          </Link>
        ))}
        <div className="pb-safe" />
      </div>

      {/* Tab bar */}
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

        {/* More tab */}
        <button
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-ink-3 relative"
          aria-label="More navigation options"
        >
          {isOverflowActive && (
            <span className="absolute top-2 right-[calc(50%-14px)] size-1.5 rounded-full bg-ink" />
          )}
          <MoreHorizontal
            className={`size-5 shrink-0 ${isOverflowActive ? 'text-ink' : ''}`}
            aria-hidden
          />
          <span className={`text-[10px] mono ${isOverflowActive ? 'font-semibold text-ink' : ''}`}>
            More
          </span>
        </button>
      </nav>
    </>
  )
}
