import {
  HeadContent,
  Link,
  Outlet,
  Scripts,
  createRootRoute,
} from '@tanstack/react-router'
import * as React from 'react'
import appCss from '~/styles/app.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'AI Portal — Self-hosted AI for teams' },
      {
        name: 'description',
        content:
          'AI Portal gives your team private, self-hosted access to LLMs with knowledge bases, memory, and full data control.',
      },
    ],
    links: [
      { rel: 'stylesheet', href: appCss },
      { rel: 'icon', href: '/favicon.ico' },
    ],
  }),
  component: RootComponent,
})

function RootComponent() {
  return (
    <RootDocument>
      <Outlet />
    </RootDocument>
  )
}

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="antialiased">
      <head>
        <HeadContent />
      </head>
      <body className="bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-100">
        <Nav />
        <main>{children}</main>
        <Footer />
        <Scripts />
      </body>
    </html>
  )
}

const APP_URL = import.meta.env.VITE_APP_URL ?? 'https://app.example.com'

function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-gray-100 bg-white/80 backdrop-blur dark:border-gray-800 dark:bg-gray-950/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
          <span className="text-xl">🤖</span>
          <span>AI Portal</span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm font-medium text-gray-600 dark:text-gray-400 sm:flex">
          <Link to="/features" className="hover:text-gray-900 dark:hover:text-white transition-colors">
            Features
          </Link>
          <Link to="/pricing" className="hover:text-gray-900 dark:hover:text-white transition-colors">
            Pricing
          </Link>
        </nav>
        <div className="flex items-center gap-3">
          <a
            href={`${APP_URL}/login`}
            className="text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors"
          >
            Sign in
          </a>
          <a
            href={`${APP_URL}/register`}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Get started
          </a>
        </div>
      </div>
    </header>
  )
}

function Footer() {
  return (
    <footer className="border-t border-gray-100 dark:border-gray-800 py-12">
      <div className="mx-auto max-w-6xl px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-500 dark:text-gray-400">
        <span>© {new Date().getFullYear()} AI Portal. All rights reserved.</span>
        <nav className="flex items-center gap-6">
          <Link to="/features" className="hover:text-gray-900 dark:hover:text-white transition-colors">
            Features
          </Link>
          <Link to="/pricing" className="hover:text-gray-900 dark:hover:text-white transition-colors">
            Pricing
          </Link>
        </nav>
      </div>
    </footer>
  )
}
