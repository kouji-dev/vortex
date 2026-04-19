// landing/src/components/LogoBand.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'

const LOGOS = ['Anthropic','OpenAI','Vercel','Linear','Notion','Stripe','Cloudflare','Figma']
const TRACK = [...LOGOS, ...LOGOS] // doubled for seamless CSS marquee loop

export function LogoBand() {
  const ref = useScrollReveal<HTMLDivElement>()

  return (
    <div ref={ref} className="reveal" style={{ padding: '40px 0', overflow: 'hidden' }}>
      <div style={{ textAlign: 'center', fontSize: 11, letterSpacing: '.14em', textTransform: 'uppercase', color: '#1e1e35', fontWeight: 700, marginBottom: 22 }}>
        Trusted by teams at
      </div>
      <div style={{ overflow: 'hidden', WebkitMaskImage: 'linear-gradient(90deg,transparent,black 12%,black 88%,transparent)', maskImage: 'linear-gradient(90deg,transparent,black 12%,black 88%,transparent)' }}>
        <div style={{ display: 'flex', gap: 52, width: 'max-content', animation: 'ticker 22s linear infinite', alignItems: 'center' }}>
          {TRACK.map((name, i) => (
            <span key={i} style={{ fontSize: 13, fontWeight: 700, color: '#1e1e35', whiteSpace: 'nowrap' }}>{name}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
