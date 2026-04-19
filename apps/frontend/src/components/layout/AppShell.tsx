import type { ReactNode } from 'react'

import { AppSidebar } from '~/components/layout/AppSidebar'
import { AppTopbar } from '~/components/layout/AppTopbar'

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app">
      <AppTopbar />
      <AppSidebar />
      <main className="main" data-testid="app-main">
        {children}
      </main>
    </div>
  )
}
