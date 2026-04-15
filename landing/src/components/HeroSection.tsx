// landing/src/components/HeroSection.tsx
import * as React from 'react'

const DEMO_MODEL = '{DEMO_MODEL}'

const PRISM_SVG_SMALL = (
  <svg width="18" height="18" viewBox="0 0 80 80" fill="none">
    <defs><linearGradient id="hero-sidebar-prism-grad" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse"><stop offset="0%" stopColor="#f472b6"/><stop offset="50%" stopColor="#a78bfa"/><stop offset="100%" stopColor="#60a5fa"/></linearGradient></defs>
    <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#hero-sidebar-prism-grad)" strokeWidth="3"/>
    <circle cx="40" cy="40" r="4" fill="#a78bfa"/>
  </svg>
)

const SEND_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="14" height="14">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

const chatIcon = (w = 14) => (
  <svg style={{ width: w, height: w, opacity: .6 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
)

const kbIcon = (w = 14) => (
  <svg style={{ width: w, height: w, opacity: .6 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
  </svg>
)

export function HeroSection() {
  const threadRef    = React.useRef<HTMLDivElement>(null)
  const composerRef  = React.useRef<HTMLTextAreaElement>(null)
  const charCountRef = React.useRef<HTMLSpanElement>(null)
  const sendBtnRef   = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    let cleanup: (() => void) | undefined
    let aborted = false
    // Lazy-import to avoid SSR issues
    import('~/lib/demo-hero').then(({ startHeroDemo }) => {
      if (aborted) return
      if (!threadRef.current || !composerRef.current || !charCountRef.current || !sendBtnRef.current) return
      cleanup = startHeroDemo({
        thread:    threadRef.current,
        composer:  composerRef.current,
        charCount: charCountRef.current,
        sendBtn:   sendBtnRef.current,
      })
    })
    return () => {
      aborted = true
      cleanup?.()
    }
  }, [])

  return (
    <section style={{ position: 'relative', overflow: 'hidden', minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '100px 24px 60px' }}>
      {/* Background */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 80% 60% at 50% 20%,rgba(167,139,250,.07) 0%,transparent 70%),radial-gradient(ellipse 50% 40% at 20% 80%,rgba(244,114,182,.04) 0%,transparent 60%),radial-gradient(ellipse 50% 40% at 80% 80%,rgba(96,165,250,.04) 0%,transparent 60%)', animation: 'bgBreath 8s ease-in-out infinite' }}/>
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(167,139,250,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(167,139,250,.03) 1px,transparent 1px)', backgroundSize: '64px 64px', maskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%,black 30%,transparent 100%)', WebkitMaskImage: 'radial-gradient(ellipse 80% 80% at 50% 50%,black 30%,transparent 100%)' }}/>
      </div>

      {/* Content */}
      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: 1000 }}>

        {/* Badge */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 14px 5px 8px', background: 'rgba(167,139,250,.06)', border: '1px solid rgba(167,139,250,.18)', borderRadius: 100, fontSize: 12, color: '#a78bfa', fontWeight: 500, fontFamily: 'monospace', marginBottom: 40, animation: 'fadeDown .7s ease both' }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', animation: 'dotPulse 2s ease-in-out infinite' }}/>
          prod server&nbsp;&nbsp;<span style={{ color: '#2a2a3e' }}>/</span>&nbsp;&nbsp;running
        </div>

        <p style={{ fontSize: 13, fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--violet)', marginBottom: 18, animation: 'fadeDown .7s ease .1s both' }}>AI Portal · Built for Teams</p>

        <h1 style={{ fontSize: 'clamp(40px,6vw,76px)', fontWeight: 900, letterSpacing: '-.055em', lineHeight: .95, textAlign: 'center', marginBottom: 24, animation: 'fadeUp .8s ease .2s both' }}>
          <span style={{ display: 'block', color: 'var(--text)' }}>Ask anything.</span>
          <span style={{ display: 'block', margin: '6px 0' }}>
            <span style={{ background: 'linear-gradient(100deg,var(--pink) 0%,var(--violet) 45%,var(--blue) 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', backgroundSize: '400% 100%', backgroundPosition: '100% 0', animation: 'shineSweep 5s ease-in-out .8s forwards' }}>
              Know everything.
            </span>
          </span>
          <span style={{ display: 'block', color: 'rgba(232,228,255,.28)', fontWeight: 800 }}>Ship faster.</span>
        </h1>

        <p style={{ fontSize: 18, color: 'var(--muted)', maxWidth: 500, lineHeight: 1.7, textAlign: 'center', marginBottom: 40, animation: 'fadeUp .8s ease .35s both' }}>
          Stop switching between AI tools and repeating context.{' '}
          <strong style={{ color: '#94a3b8', fontWeight: 500 }}>Vortex connects the best models to your knowledge, memory, and team</strong> — in one place.
        </p>

        <div style={{ display: 'flex', gap: 14, alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap', marginBottom: 60, animation: 'fadeUp .8s ease .5s both' }}>
          <a href="#" style={{ padding: '14px 32px', background: 'linear-gradient(135deg,var(--pink),var(--violet) 60%,var(--blue))', color: '#fff', fontSize: 15, fontWeight: 700, borderRadius: 10, border: 'none', textDecoration: 'none', letterSpacing: '-.01em', boxShadow: '0 4px 32px rgba(167,139,250,.3)' }}>Start for free →</a>
          <a href="#hiw" style={{ padding: '14px 28px', background: 'transparent', border: '1px solid var(--b2)', color: '#4b5563', fontSize: 15, fontWeight: 500, borderRadius: 10, textDecoration: 'none' }}>See how it works</a>
        </div>

        {/* App demo frame */}
        <div style={{ width: '100%', maxWidth: 960, animation: 'fadeUp .9s ease .65s both' }}>
          <div style={{ background: '#0a0a12', border: '1px solid rgba(167,139,250,.12)', borderRadius: 16, overflow: 'hidden', boxShadow: '0 48px 120px rgba(0,0,0,.85),0 0 80px rgba(167,139,250,.05)' }}>
            {/* Title bar */}
            <div style={{ background: '#0c0c18', borderBottom: '1px solid var(--border)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
              {[0,1,2].map(i => <div key={i} style={{ width: 8, height: 8, borderRadius: '50%', background: '#2a2a3e' }}/>)}
              <div style={{ marginLeft: 12, flex: 1, background: '#111122', border: '1px solid var(--border)', borderRadius: 5, padding: '4px 10px', fontSize: 11, color: '#374151', fontFamily: 'monospace' }}>vortex.app/chat/conversations/42</div>
            </div>

            {/* App shell */}
            <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', height: 520 }}>
              {/* Sidebar */}
              <div style={{ background: '#060610', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  {PRISM_SVG_SMALL}
                  <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: '-.03em', background: 'linear-gradient(90deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>Vortex</span>
                </div>
                <div style={{ padding: '8px 0', flex: 1 }}>
                  {[
                    { label: 'Conversations', isSection: true },
                    { label: 'Q3 Risk Analysis', active: true },
                    { label: 'Product roadmap 2026' },
                    { label: 'Engineering runbook' },
                    { label: 'Knowledge Bases', isSection: true },
                    { label: 'Finance Docs', isKb: true },
                    { label: 'Product Specs', isKb: true },
                  ].map((item, i) => item.isSection
                    ? <div key={item.label} style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: '#1e1e35', padding: '6px 14px 4px', marginTop: i > 0 ? 8 : 0 }}>{item.label}</div>
                    : <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', fontSize: 12, color: item.active ? '#c4b5fd' : '#374151', background: item.active ? 'rgba(167,139,250,.08)' : 'transparent' }}>
                        {item.isKb ? kbIcon() : chatIcon()}
                        {item.label}
                      </div>
                  )}
                </div>
              </div>

              {/* Chat */}
              <div style={{ display: 'flex', flexDirection: 'column', background: '#07070e' }}>
                <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#6b7280' }}>Q3 Risk Analysis</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: 'rgba(167,139,250,.06)', border: '1px solid rgba(167,139,250,.12)', borderRadius: 5, fontSize: 10, color: '#a78bfa', fontFamily: 'monospace' }}>
                    <svg viewBox="0 0 80 80" fill="none" width="10" height="10"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="#a78bfa" strokeWidth="4"/></svg>
                    {DEMO_MODEL}
                  </div>
                </div>

                <div ref={threadRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 16 }}/>

                {/* Composer */}
                <div style={{ borderTop: '1px solid var(--border)', padding: '10px 14px', background: '#060610' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
                    <span className="cap-tag cap-reflection">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/><path d="M11.5 11.5h8"/></svg>
                      Reflection
                    </span>
                    <span className="cap-tag cap-research">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                      Research
                    </span>
                    <span className="kb-tag">
                      {kbIcon(10)}
                      Finance Docs
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                    <textarea ref={composerRef} className="composer-textarea" placeholder="Message Vortex…" rows={1} readOnly/>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
                      <div style={{ fontSize: 10, color: '#374151', fontFamily: 'monospace', border: '1px solid var(--border)', background: '#0a0a18', borderRadius: 5, padding: '3px 6px' }}>{DEMO_MODEL} ▾</div>
                      <button ref={sendBtnRef} style={{ width: 32, height: 32, borderRadius: 8, border: 'none', cursor: 'pointer', background: 'linear-gradient(135deg,var(--pink),var(--violet))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {SEND_ICON}
                      </button>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                    <span style={{ fontSize: 10, color: '#2a2a3e', padding: '2px 6px', border: '1px solid var(--border)', borderRadius: 4 }}>📎 Attach</span>
                    <span ref={charCountRef} style={{ fontSize: 10, color: '#1e1e35', marginLeft: 'auto' }}>0 / 2000</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
