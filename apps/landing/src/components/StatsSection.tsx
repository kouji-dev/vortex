// landing/src/components/StatsSection.tsx — Landing v2 design
import * as React from 'react'
import { useCountUp } from '~/hooks/useCountUp'
import { useScrollReveal } from '~/hooks/useScrollReveal'

interface StatProps {
  label: string
  value?: number
  sym?: string
  suffix?: string
  sub: string
  delay?: number
}

function Stat({ label, value, sym, suffix, sub, delay, last }: StatProps & { last?: boolean }) {
  const numRef = useCountUp(value ?? 0)
  return (
    <div
      className="reveal"
      style={{
        textAlign: 'left', paddingRight: 20,
        borderRight: last ? '0' : '1px solid var(--border)',
        transitionDelay: delay ? `${delay}ms` : undefined,
      }}
    >
      <div style={{
        fontFamily: '"JetBrains Mono", monospace', fontSize: 11,
        color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.12em',
        marginBottom: 6,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 56, fontWeight: 600, letterSpacing: '-0.03em', lineHeight: 1,
        background: 'var(--g-grad)',
        WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
        fontVariantNumeric: 'tabular-nums',
        marginBottom: 10,
      }}>
        {sym ? sym : (
          <>{value !== undefined ? <span ref={numRef as any}>0</span> : null}{suffix}</>
        )}
      </div>
      <div style={{ color: 'var(--text-2)', fontSize: 13 }}>{sub}</div>
    </div>
  )
}

export function StatsSection() {
  const ref = useScrollReveal<HTMLDivElement>()
  return (
    <div
      ref={ref}
      className="reveal"
      style={{
        maxWidth: 1280, margin: '0 auto',
        padding: '80px 32px',
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 32,
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <Stat label="Models"      value={10}  suffix="+" sub="Anthropic · OpenAI · Google · Mistral · open-source" delay={100}/>
      <Stat label="KB size"     sym="∞"               sub="Ingest millions of documents. pgvector + rerank."     delay={200}/>
      <Stat label="Self-host"   value={100} suffix="%" sub="One Docker Compose. Your data never leaves."         delay={300}/>
      <Stat label="First token" sym="<1s"              sub="Streaming from turn one. No cold-start tax."         delay={400} last/>
    </div>
  )
}
