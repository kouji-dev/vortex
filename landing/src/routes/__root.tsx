// landing/src/routes/__root.tsx
import { HeadContent, Link, Outlet, Scripts, createRootRoute } from '@tanstack/react-router'
import * as React from 'react'
import { getAppUrl } from '~/lib/app-url'
import appCss from '~/styles/app.css?url'

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Vortex — AI Portal for Teams' },
      { name: 'description', content: 'Vortex connects the best AI models to your knowledge, memory, and team — in one place.' },
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
    <html lang="en" style={{ background: 'var(--bg)' }}>
      <head><HeadContent /></head>
      <body style={{ background: 'var(--bg)', color: 'var(--text)', overflowX: 'hidden', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
        <AnnounceBanner />
        <VortexNav />
        <main><Outlet /></main>
        <VortexFooter />
        <Scripts />
      </body>
    </html>
  )
}

function AnnounceBanner() {
  return (
    <div style={{ background: 'linear-gradient(90deg,transparent,rgba(167,139,250,.07),transparent)', borderBottom: '1px solid rgba(167,139,250,.12)', textAlign: 'center', padding: '9px 16px', fontSize: 12, color: '#a78bfa', fontWeight: 500, letterSpacing: '.04em' }}>
      <em style={{ color: 'var(--pink)', fontStyle: 'normal', fontWeight: 700, marginRight: 4 }}>✦ NEW</em>
      Vortex supports web search, multi-model routing &amp; persistent memory —{' '}
      <a href="#" style={{ color: '#c4b5fd' }}>Changelog →</a>
    </div>
  )
}

const PRISM_NAV = (
  <svg width="24" height="24" viewBox="0 0 80 80" fill="none">
    <defs>
      <linearGradient id="ng" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#f472b6"/>
        <stop offset="50%" stopColor="#a78bfa"/>
        <stop offset="100%" stopColor="#60a5fa"/>
      </linearGradient>
    </defs>
    <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#ng)" strokeWidth="2.5"/>
    <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" opacity=".5"/>
    <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" opacity=".5"/>
    <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" opacity=".5"/>
    <circle cx="40" cy="40" r="4" fill="#e0d7ff"/>
  </svg>
)

function VortexNav() {
  return (
    <nav style={{ position: 'sticky', top: 0, zIndex: 100, display: 'flex', alignItems: 'center', padding: '0 56px', height: 60, background: 'rgba(4,4,7,.85)', backdropFilter: 'blur(20px)', borderBottom: '1px solid rgba(22,22,40,.8)' }}>
      <a href="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
        {PRISM_NAV}
        <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-.04em', background: 'linear-gradient(90deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Vortex</span>
      </a>
      <ul style={{ display: 'flex', gap: 32, marginLeft: 40, listStyle: 'none' }}>
        {['Features','Docs','Blog'].map(l => (
          <li key={l}><a href="#" style={{ color: '#4b5563', textDecoration: 'none', fontSize: 14, fontWeight: 500 }}>{l}</a></li>
        ))}
      </ul>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center' }}>
        <a href={`${getAppUrl()}/login`} style={{ padding: '7px 18px', background: 'transparent', border: '1px solid var(--b2)', color: '#4b5563', fontSize: 13, fontWeight: 500, borderRadius: 7, textDecoration: 'none' }}>Sign in</a>
        <a href={`${getAppUrl()}/register`} style={{ padding: '8px 20px', background: 'linear-gradient(135deg,#f472b6,#a78bfa 60%,#60a5fa)', color: '#fff', fontSize: 13, fontWeight: 600, borderRadius: 7, textDecoration: 'none', boxShadow: '0 0 20px rgba(167,139,250,.25)' }}>Get started</a>
      </div>
    </nav>
  )
}

function VortexFooter() {
  const cols = [
    { head: 'Product',    links: ['Chat','Knowledge Bases','Memory','Changelog'] },
    { head: 'Developers', links: ['Docs','API','GitHub','Self-hosting'] },
    { head: 'Company',    links: ['About','Blog','Privacy','Terms'] },
  ]
  return (
    <footer style={{ background: '#020205', borderTop: '1px solid var(--border)', padding: '56px 56px 32px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 48, marginBottom: 48 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <svg width="18" height="18" viewBox="0 0 80 80" fill="none"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="#a78bfa" strokeWidth="3"/><circle cx="40" cy="40" r="4" fill="#a78bfa"/></svg>
            <span style={{ fontSize: 15, fontWeight: 700, background: 'linear-gradient(90deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Vortex</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--dim)', lineHeight: 1.7, maxWidth: 240 }}>The AI portal for teams. Chat, search, remember — all in one place.</p>
        </div>
        {cols.map(c => (
          <div key={c.head}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--dim)', marginBottom: 16 }}>{c.head}</div>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 11 }}>
              {c.links.map(l => <li key={l}><a href="#" style={{ fontSize: 13, color: '#1e1e35', textDecoration: 'none' }}>{l}</a></li>)}
            </ul>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 24, borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--dim)' }}>
        <span>© 2026 Vortex. All rights reserved.</span>
        <span>Built with ♥ and Claude</span>
      </div>
    </footer>
  )
}
