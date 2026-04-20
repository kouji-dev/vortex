// landing/src/components/CTASection.tsx — Landing v2 design
import * as React from 'react'
import { getAppUrl } from '~/lib/app-url'

export function CTASection() {
  return (
    <section style={{
      maxWidth: 1280, margin: '0 auto',
      padding: '120px 32px',
      textAlign: 'center',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Radial glow */}
      <div style={{
        position: 'absolute', left: '50%', bottom: -200, transform: 'translateX(-50%)',
        width: 900, height: 500,
        background: 'radial-gradient(ellipse at center, rgba(167,139,250,0.3), transparent 60%)',
        pointerEvents: 'none', filter: 'blur(20px)',
      }}/>

      <h2
        className="reveal"
        style={{
          position: 'relative',
          margin: '0 0 18px',
          fontSize: 64, fontWeight: 600,
          letterSpacing: '-0.03em', lineHeight: 1.02,
        }}
      >
        Ask anything.{' '}
        <em style={{ background: 'var(--g-grad)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', fontStyle: 'normal' }}>
          Know everything.
        </em>
      </h2>

      <p className="reveal" style={{ position: 'relative', fontSize: 18, color: 'var(--text-2)', marginBottom: 32 }}>
        Join the public beta. Sign in with Google, GitHub, or email. It takes about 12 seconds.
      </p>

      <div className="reveal" style={{ position: 'relative', display: 'flex', gap: 10, justifyContent: 'center' }}>
        <a className="btn btn-grad" href={`${getAppUrl()}/register`}>
          <span className="inner">Start for free <span>→</span></span>
        </a>
        <a className="btn" href="#">Read the docs</a>
      </div>
    </section>
  )
}
