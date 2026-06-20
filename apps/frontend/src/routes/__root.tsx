/// <reference types="vite/client" />
import {
  HeadContent,
  Outlet,
  Scripts,
  createRootRouteWithContext,
  useRouterState,
} from '@tanstack/react-router'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import * as React from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { EntraRoot } from '~/auth/EntraRoot'
import { getAuthMode } from '~/auth/msalConfig'
import { DefaultCatchBoundary } from '~/components/DefaultCatchBoundary'
import { AppShell } from '~/components/layout/AppShell'
import { MobileAppShell } from '~/components/layout/MobileAppShell'
import { useIsMobile } from '~/hooks/useIsMobile'
import { NotFound } from '~/components/NotFound'
import appCss from '~/styles/app.css?url'
import { seo } from '~/utils/seo'
import { useAuthRedirect } from '~/hooks/useAuthRedirect'
import { useMeQuery } from '~/hooks/useMeQuery'
import { useRealtimeEvents } from '~/hooks/useRealtimeEvents'
import { useSetupRedirect } from '~/hooks/useSetupRedirect'
import { bootstrapTheme } from '~/hooks/useTheme'

if (typeof window !== 'undefined') {
  bootstrapTheme()
}

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient
}>()({
  head: () => ({
    scripts: [
      {
        children: `(function(){try{var t=localStorage.getItem('vx.theme');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);return;}var m=window.matchMedia('(prefers-color-scheme: dark)');document.documentElement.setAttribute('data-theme',m.matches?'dark':'light');}catch(e){}})()`,
      },
    ],
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1',
      },
      ...seo({
        title: 'AI Portal',
        description: 'Authenticated AI portal — chat with conversations and streaming.',
      }),
    ],
    links: [
      { rel: 'stylesheet', href: appCss },
      { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
      { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: '' },
      { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@500;600&display=swap' },
      {
        rel: 'apple-touch-icon',
        sizes: '180x180',
        href: '/apple-touch-icon.png',
      },
      {
        rel: 'icon',
        type: 'image/png',
        sizes: '32x32',
        href: '/favicon-32x32.png',
      },
      {
        rel: 'icon',
        type: 'image/png',
        sizes: '16x16',
        href: '/favicon-16x16.png',
      },
      { rel: 'manifest', href: '/site.webmanifest', color: '#fffff' },
      { rel: 'icon', href: '/favicon.ico' },
    ],
  }),
  errorComponent: (props) => {
    return (
      <RootDocument>
        <div className="h-dvh overflow-y-auto overscroll-contain bg-gray-50 dark:bg-gray-950">
          <DefaultCatchBoundary {...props} />
        </div>
      </RootDocument>
    )
  },
  notFoundComponent: () => <NotFound />,
  component: RootComponent,
})

const AUTH_ROUTE_RE = /^\/(login|register|setup)(\/|$)/

function RootComponent() {
  // Deterministic hydration marker for E2E: a useEffect commits only after the
  // client has hydrated, so `html[data-hydrated]` signals the tree is interactive.
  React.useEffect(() => {
    document.documentElement.dataset.hydrated = 'true'
    return () => {
      delete document.documentElement.dataset.hydrated
    }
  }, [])

  useAuthRedirect()
  useSetupRedirect()
  const me = useMeQuery()
  useRealtimeEvents(me.isSuccess)
  const { isMobile } = useIsMobile()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const isAuthRoute = AUTH_ROUTE_RE.test(pathname)

  const content = isAuthRoute ? (
    <Outlet />
  ) : isMobile ? (
    <MobileAppShell>
      <Outlet />
    </MobileAppShell>
  ) : (
    <AppShell>
      <Outlet />
    </AppShell>
  )

  return (
    <RootDocument>
      {getAuthMode() === 'entra' ? <EntraRoot>{content}</EntraRoot> : content}
    </RootDocument>
  )
}

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  )
}
