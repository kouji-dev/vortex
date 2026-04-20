// landing/src/components/MissionSection.tsx — Landing v2 design
import * as React from 'react'

export function MissionSection() {
  return (
    <section
      className="reveal"
      style={{
        maxWidth: 900, margin: '0 auto',
        padding: '140px 32px',
        textAlign: 'center',
      }}
    >
      {/* Big prism */}
      <div style={{ margin: '0 auto 32px', width: 80, height: 80 }}>
        <svg viewBox="0 0 80 80" width="80" height="80">
          <defs>
            <linearGradient id="pgBig" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#f472b6"/>
              <stop offset="50%" stopColor="#a78bfa"/>
              <stop offset="100%" stopColor="#60a5fa"/>
            </linearGradient>
          </defs>
          <g style={{ transformOrigin: '40px 40px', animation: 'prismPendulum 1.8s ease-in-out infinite' }}>
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#pgBig)" strokeWidth="2" strokeLinejoin="round"/>
            <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.3" opacity="0.65"/>
            <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.3" opacity="0.65"/>
            <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.3" opacity="0.65"/>
            <circle cx="40" cy="40" r="4" fill="#e0d7ff"/>
          </g>
        </svg>
      </div>

      <h2 style={{ margin: '0 0 24px', fontSize: 42, fontWeight: 500, letterSpacing: '-0.025em', lineHeight: 1.2 }}>
        We believe every team should be able to{' '}
        <em style={{ background: 'var(--g-grad)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', fontWeight: 600, fontStyle: 'normal' }}>
          talk to their work
        </em>
        {' '}— without handing their data to a black box.
      </h2>

      <p style={{ color: 'var(--text-2)', fontSize: 17, lineHeight: 1.6 }}>
        Vortex is open-source at the core, self-hostable end to end, and built for teams that take their own context seriously.
      </p>
    </section>
  )
}
