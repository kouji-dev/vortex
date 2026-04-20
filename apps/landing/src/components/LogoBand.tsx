// landing/src/components/LogoBand.tsx — Landing v2 design
import * as React from 'react'

const LOGOS = ['Northwind', 'Kestrel Labs', 'Meridian', 'Halcyon', 'Runway Systems', 'Basecase', 'Atlas Robotics', 'Vellum']
const TRACK = [...LOGOS, ...LOGOS] // doubled for seamless marquee loop

export function LogoBand() {
  return (
    <div style={{
      maxWidth: 1280, margin: '0 auto',
      padding: '40px 32px',
      borderTop: '1px solid var(--border)',
      borderBottom: '1px solid var(--border)',
      overflow: 'hidden', position: 'relative',
    }}>
      <div style={{
        fontFamily: '"JetBrains Mono", ui-monospace, monospace', fontSize: 11,
        color: 'var(--muted)', textAlign: 'center',
        textTransform: 'uppercase', letterSpacing: '0.15em',
        marginBottom: 24,
      }}>
        Teams shipping with Vortex
      </div>
      <div style={{
        display: 'flex', gap: 64,
        animation: 'marquee 28s linear infinite',
        width: 'max-content',
        maskImage: 'linear-gradient(90deg, transparent 0%, #000 10%, #000 90%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(90deg, transparent 0%, #000 10%, #000 90%, transparent 100%)',
      }}>
        {TRACK.map((name, i) => (
          <span
            key={i}
            style={{
              fontFamily: '"JetBrains Mono", ui-monospace, monospace',
              fontWeight: 600, fontSize: 20,
              color: 'var(--muted)', whiteSpace: 'nowrap',
              letterSpacing: '-0.015em',
              display: 'inline-flex', alignItems: 'center', gap: 10,
              opacity: 0.7,
            }}
          >
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--dim)', display: 'inline-block' }}/>
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}
