import type { ReactNode } from 'react'
import * as React from 'react'

import { AppSidebar } from '~/components/layout/AppSidebar'

const STORAGE_KEY = 'ai-portal-sidebar-compact'

export function AppShell({ children }: { children: ReactNode }) {
  const [sidebarCompact, setSidebarCompact] = React.useState(false)
  const [hydrated, setHydrated] = React.useState(false)

  React.useEffect(() => {
    try {
      setSidebarCompact(localStorage.getItem(STORAGE_KEY) === '1')
    } catch {
      /* ignore */
    }
    setHydrated(true)
  }, [])

  const toggleSidebarCompact = React.useCallback(() => {
    setSidebarCompact((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-white dark:bg-neutral-950">
      <AppSidebar
        compact={hydrated && sidebarCompact}
        onToggleCompact={toggleSidebarCompact}
      />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  )
}
