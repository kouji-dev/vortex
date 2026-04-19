// landing/src/components/StatsSection.tsx
import * as React from 'react'
import { useScrollReveal } from '~/hooks/useScrollReveal'
import { useCountUp } from '~/hooks/useCountUp'

function CountStat({ target, suffix, sym, label }: { target?: number; suffix?: string; sym?: string; label: string }) {
  const numRef = useCountUp(target ?? 0)
  return (
    <div style={{ padding: '52px 28px', textAlign: 'center', borderRight: '1px solid var(--border)', position: 'relative', flex: 1 }}>
      <div style={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', width: '60%', height: 1, background: 'linear-gradient(90deg,transparent,rgba(167,139,250,.25),transparent)' }}/>
      <div style={{ fontSize: 48, fontWeight: 900, letterSpacing: '-.06em', lineHeight: 1, background: 'linear-gradient(135deg,var(--pink),var(--violet))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 8 }}>
        {sym ? sym : <><span ref={numRef as any}>{target ? '0' : '0'}</span>{suffix}</>}
      </div>
      <div style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500, lineHeight: 1.4 }} dangerouslySetInnerHTML={{ __html: label }}/>
    </div>
  )
}

export function StatsSection() {
  const ref = useScrollReveal<HTMLDivElement>()
  return (
    <div ref={ref} className="reveal" style={{ display: 'flex', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
      <CountStat target={10} suffix="+"  label="AI models<br/>supported"/>
      <CountStat sym="∞"                 label="Knowledge base<br/>size limit"/>
      <CountStat target={100} suffix="%" label="Self-hostable &amp;<br/>open source"/>
      <CountStat sym="&lt;1s"            label="First token<br/>latency"/>
    </div>
  )
}
