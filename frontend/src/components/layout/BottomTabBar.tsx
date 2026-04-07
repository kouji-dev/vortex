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
      {moreOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={() => setMoreOpen(false)}
          aria-hidden
        />
      )}

      {/* More sheet */}
      {moreOpen && (
        <div className="fixed bottom-0 inset-x-0 z-50 rounded-t-2xl border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950 transition-transform duration-200 ease-out">
          <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700" />
          <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            More
          </p>
          {OVERFLOW_ITEMS.map(({ to, icon: Icon, label }) => (
            <Link
              key={to}
              to={to}
              onClick={() => setMoreOpen(false)}
              className="flex items-center gap-3 px-4 py-3 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              <Icon className="size-5 shrink-0 text-neutral-500 dark:text-neutral-400" aria-hidden />
              {label}
            </Link>
          ))}
          <div className="pb-safe" />
        </div>
      )}

      {/* Tab bar */}
      <nav
        className="flex shrink-0 items-stretch border-t border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-950"
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
              className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-neutral-500 dark:text-neutral-400"
              activeProps={{}}
            >
              <Icon
                className={`size-5 shrink-0 ${active ? 'text-neutral-900 dark:text-neutral-100' : ''}`}
                aria-hidden
              />
              <span
                className={`text-[10px] ${active ? 'font-semibold text-neutral-900 dark:text-neutral-100' : ''}`}
              >
                {label}
              </span>
            </Link>
          )
        })}

        {/* More tab */}
        <button
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-neutral-500 dark:text-neutral-400 relative"
          aria-label="More navigation options"
        >
          {isOverflowActive && (
            <span className="absolute top-2 right-[calc(50%-14px)] size-1.5 rounded-full bg-neutral-900 dark:bg-neutral-100" />
          )}
          <MoreHorizontal
            className={`size-5 shrink-0 ${isOverflowActive ? 'text-neutral-900 dark:text-neutral-100' : ''}`}
            aria-hidden
          />
          <span className={`text-[10px] ${isOverflowActive ? 'font-semibold text-neutral-900 dark:text-neutral-100' : ''}`}>
            More
          </span>
        </button>
      </nav>
    </>
  )
}
