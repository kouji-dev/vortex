// landing/src/routes/__root.tsx
import { HeadContent, Outlet, Scripts, createRootRoute } from '@tanstack/react-router'
import * as React from 'react'
import { getAppUrl } from '~/lib/app-url'
import appCss from '~/styles/app.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Vortex — Ask anything. Know everything.' },
      { name: 'description', content: 'Vortex is the AI portal your team actually wants to use. One chat for every model. Your knowledge, your memory, your guardrails — under one roof.' },
    ],
    links: [
      { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
      { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: 'anonymous' },
      { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap' },
      { rel: 'stylesheet', href: appCss },
      { rel: 'icon', href: '/favicon.ico' },
    ],
  }),
  component: RootComponent,
})

function RootComponent() {
  return (
    <html lang="en">
      <head><HeadContent /></head>
      <body>
        <AnnounceBanner />
        <VortexNav />
        <main><Outlet /></main>
        <VortexFooter />
        <div className="copybar">
          <span>© {new Date().getFullYear()} Vortex · Made for teams</span>
          <span style={{ display: 'flex', gap: 16 }}>
            <a href="#">v1.0.0-beta</a>
            <a href="#">status · operational</a>
          </span>
        </div>
        <Scripts />
      </body>
    </html>
  )
}

function AnnounceBanner() {
  return (
    <div className="annbar">
      <div className="annbar-inner">
        <span className="pill">beta</span>
        <span>Vortex is open for public beta — Google, GitHub, or email to get in.</span>
        <span style={{ color: 'var(--violet)' }}>→</span>
      </div>
    </div>
  )
}

/* ── Prism SVG (reused in nav + footer) ── */
const PrismNav = ({ size = 28 }: { size?: number }) => (
  <svg viewBox="0 0 80 80" width={size} height={size} style={{ display: 'block' }}>
    <defs>
      <linearGradient id="pgNav" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#f472b6"/>
        <stop offset="50%" stopColor="#a78bfa"/>
        <stop offset="100%" stopColor="#60a5fa"/>
      </linearGradient>
    </defs>
    <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#pgNav)" strokeWidth="2.5" strokeLinejoin="round"/>
    <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" opacity="0.6"/>
    <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" opacity="0.6"/>
    <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" opacity="0.6"/>
    <circle cx="40" cy="40" r="4" fill="#e0d7ff"/>
  </svg>
)

function VortexNav() {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <a className="brand" href="/">
          <span className="prism idle" style={{ width: 28, height: 28 }}>
            <PrismNav size={28} />
          </span>
          <span className="wm">Vortex</span>
        </a>
        <div className="nav-links">
          <a href="#features">Features</a>
          <a href="#how">How it works</a>
          <a href="#">Docs</a>
          <a href="#">Blog</a>
          <a href="#">Changelog</a>
        </div>
        <div className="nav-cta">
          <a className="btn btn-ghost" href={`${getAppUrl()}/login`}>Sign in</a>
          <a className="btn btn-grad" href={`${getAppUrl()}/register`}>
            <span className="inner">Get started <span style={{ transition: 'transform 160ms' }}>→</span></span>
          </a>
        </div>
      </div>
    </nav>
  )
}

function VortexFooter() {
  return (
    <footer>
      <div>
        <div className="brand" style={{ marginBottom: 12 }}>
          <span className="prism idle" style={{ width: 22, height: 22 }}>
            <PrismNav size={22} />
          </span>
          <span className="wm">Vortex</span>
        </div>
        <p className="tag">The AI portal your team actually wants to use. Open-source. Self-hostable. Enterprise-ready.</p>
      </div>
      <div>
        <h4>Product</h4>
        <ul>
          <li><a href={`${getAppUrl()}/chat`}>Chat</a></li>
          <li><a href="#">Workflows</a></li>
          <li><a href="#">Knowledge</a></li>
          <li><a href="#">Memories</a></li>
          <li><a href="#">Governance</a></li>
        </ul>
      </div>
      <div>
        <h4>Developers</h4>
        <ul>
          <li><a href="#">Docs</a></li>
          <li><a href="#">API</a></li>
          <li><a href="#">Changelog</a></li>
          <li><a href="#">GitHub</a></li>
          <li><a href="#">Self-host guide</a></li>
        </ul>
      </div>
      <div>
        <h4>Company</h4>
        <ul>
          <li><a href="#">About</a></li>
          <li><a href="#">Customers</a></li>
          <li><a href="#">Security</a></li>
          <li><a href="#">Careers</a></li>
        </ul>
      </div>
      <div>
        <h4>Legal</h4>
        <ul>
          <li><a href="#">Privacy</a></li>
          <li><a href="#">Terms</a></li>
          <li><a href="#">DPA</a></li>
          <li><a href="#">Subprocessors</a></li>
        </ul>
      </div>
    </footer>
  )
}
