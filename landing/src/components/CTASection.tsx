// landing/src/components/CTASection.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'
import { getAppUrl } from '~/lib/app-url'

export function CTASection() {
  const titleRef   = useScrollReveal<HTMLHeadingElement>()
  const subRef     = useScrollReveal<HTMLParagraphElement>()
  const actionsRef = useScrollReveal<HTMLDivElement>()

  return (
    <section style={{ padding: '120px 48px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22, position: 'relative', overflow: 'hidden', background: 'var(--bg2)', borderTop: '1px solid var(--border)' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 80% 70% at 50% 100%,rgba(167,139,250,.06),transparent 60%)', pointerEvents: 'none' }}/>
      <h2 ref={titleRef} className="reveal" style={{ fontSize: 'clamp(30px,5vw,58px)', fontWeight: 900, letterSpacing: '-.05em', lineHeight: 1.05, maxWidth: 600, position: 'relative' }}>
        Your team deserves<br/>
        <span style={{ background: 'linear-gradient(90deg,var(--pink),var(--violet),var(--blue))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
          better AI tooling.
        </span>
      </h2>
      <p ref={subRef} className="reveal" style={{ fontSize: 17, color: 'var(--muted)', maxWidth: 440, lineHeight: 1.65, position: 'relative' }}>
        Start for free. No credit card. Deploy on your own infrastructure in minutes.
      </p>
      <div ref={actionsRef} className="reveal" style={{ display: 'flex', gap: 14, position: 'relative' }}>
        <a href={`${getAppUrl()}/register`} style={{ padding: '14px 32px', background: 'linear-gradient(135deg,var(--pink),var(--violet) 60%,var(--blue))', color: '#fff', fontSize: 15, fontWeight: 700, borderRadius: 10, textDecoration: 'none', boxShadow: '0 4px 32px rgba(167,139,250,.3)' }}>Get started free →</a>
        <a href="#" style={{ padding: '14px 28px', background: 'transparent', border: '1px solid var(--b2)', color: '#4b5563', fontSize: 15, fontWeight: 500, borderRadius: 10, textDecoration: 'none' }}>Talk to us</a>
      </div>
    </section>
  )
}
