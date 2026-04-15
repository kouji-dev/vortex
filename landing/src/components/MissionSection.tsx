// landing/src/components/MissionSection.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'

export function MissionSection() {
  const quoteRef = useScrollReveal<HTMLParagraphElement>()
  const attrRef  = useScrollReveal<HTMLDivElement>()
  const markRef  = useScrollReveal<HTMLDivElement>()

  return (
    <section style={{ padding: '110px 48px', textAlign: 'center', position: 'relative', overflow: 'hidden', borderTop: '1px solid var(--border)' }}>
      <div style={{ position: 'absolute', width: 800, height: 500, background: 'radial-gradient(ellipse,rgba(167,139,250,.05),transparent 70%)', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', pointerEvents: 'none' }}/>
      <div style={{ maxWidth: 780, margin: '0 auto', position: 'relative' }}>
        <div ref={markRef} className="reveal" style={{ display: 'flex', justifyContent: 'center', marginBottom: 32 }}>
          <svg width="48" height="48" viewBox="0 0 80 80" fill="none" style={{ filter: 'drop-shadow(0 0 18px rgba(167,139,250,.5))' }}>
            <defs>
              <linearGradient id="mg" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#f472b6"/><stop offset="50%" stopColor="#a78bfa"/><stop offset="100%" stopColor="#60a5fa"/>
              </linearGradient>
            </defs>
            <g style={{ animation: 'msway 4s ease-in-out infinite', transformOrigin: '40px 40px' }}>
              <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#mg)" strokeWidth="2.5"/>
              <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" opacity=".5"/>
              <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" opacity=".5"/>
              <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" opacity=".5"/>
            </g>
            <circle cx="40" cy="40" r="4.5" fill="#e0d7ff"/>
          </svg>
        </div>
        <p ref={quoteRef} className="reveal" style={{ fontSize: 'clamp(20px,2.8vw,34px)', fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.4, marginBottom: 22 }}>
          "Our mission is to make working with AI{' '}
          <span style={{ color: 'var(--violet)' }}>as natural as thinking</span>{' '}
          — so teams stop fighting their tools and start{' '}
          <span style={{ color: 'var(--pink)' }}>shipping what matters</span>."
        </p>
        <div ref={attrRef} className="reveal" style={{ fontSize: 14, color: 'var(--dim)' }}>— The Vortex team</div>
      </div>
    </section>
  )
}
