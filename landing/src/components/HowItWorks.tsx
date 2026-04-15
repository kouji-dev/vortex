// landing/src/components/HowItWorks.tsx
import * as React from 'react'
import { runChipDemo, type ChipDemoRefs } from '~/lib/demo-chips'

const TAB_DURATIONS = [5000, 11000, 5000, 5000]

const TABS = [
  { step: 'Step 01', label: 'Compose',   sub: 'Pick model, attach KB' },
  { step: 'Step 02', label: 'Process',   sub: 'Memory, KB, web search' },
  { step: 'Step 03', label: 'Knowledge', sub: 'Grounded, cited answers' },
  { step: 'Step 04', label: 'Memory',    sub: 'Learns from every session' },
]

// ─── Shared icon factories ────────────────────────────────────────────────────
const libIcon = (size = 10) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
  </svg>
)
const brainIcon = (size = 10) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/>
    <path d="M11.5 11.5h8"/>
  </svg>
)
const CHECK_ICON = (
  <svg style={{ color: '#22c55e', width: 10, height: 10 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
)
const CHEV_DOWN = (
  <svg style={{ width: 10, height: 10, opacity: .4 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="6 9 12 15 18 9"/>
  </svg>
)
const SEND_BTN_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" width="12" height="12">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

// ─── Step text column ─────────────────────────────────────────────────────────
function StepText({ n, tag, title, desc, bullets }: {
  n: string; tag: string; title: React.ReactNode
  desc: string; bullets: string[]
}) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ width: 24, height: 24, borderRadius: 6, background: 'rgba(167,139,250,.1)', border: '1px solid rgba(167,139,250,.2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: 'var(--violet)', flexShrink: 0 }}>{n}</span>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--dim)' }}>{tag}</span>
      </div>
      <h3 style={{ fontSize: 'clamp(20px,2.4vw,30px)', fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.2, marginBottom: 14 }}>{title}</h3>
      <p style={{ fontSize: 15, color: 'var(--muted)', lineHeight: 1.75, marginBottom: 18, maxWidth: 400 }}>{desc}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {bullets.map((b, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, color: '#374151', lineHeight: 1.5 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--violet)', flexShrink: 0, marginTop: 5, opacity: .5 }}/>
            {b}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Demo bar ─────────────────────────────────────────────────────────────────
function DemoBar({ label }: { label: string }) {
  return (
    <div style={{ background: '#0c0c1a', padding: '9px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 5 }}>
      {[0,1,2].map(i => <div key={i} style={{ width: 7, height: 7, borderRadius: '50%', background: '#2a2a3e' }}/>)}
      <span style={{ fontSize: 10, color: '#2a2a3e', marginLeft: 8, fontFamily: 'monospace' }}>{label}</span>
    </div>
  )
}

// ─── Panel 0: Compose ────────────────────────────────────────────────────────
function Panel0() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      <StepText
        n="1" tag="Compose"
        title={<>Any question.<br/><span style={{ color: 'var(--violet)' }}>Any model.</span></>}
        desc="Pick Claude, GPT-4o, or Gemini. Toggle Research mode for web search, Reflection for deeper reasoning. Attach a knowledge base with one click."
        bullets={['10+ models in one interface','Research + Reflection capability toggles','Attach files or knowledge bases inline']}
      />
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label="composer · claude-sonnet-4-6"/>
        <div style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            <span className="cap-tag cap-reflection">{brainIcon()} Reflection</span>
            <span className="cap-tag cap-research">{libIcon()} Research</span>
            <span className="kb-tag">{libIcon()} Finance Docs <span style={{ fontSize: 9, background: 'rgba(167,139,250,.15)', borderRadius: 3, padding: '0 4px', marginLeft: 2 }}>1</span></span>
          </div>
          <div style={{ background: '#0a0a18', border: '1px solid rgba(167,139,250,.15)', borderRadius: 9, padding: '10px 12px', fontSize: 12, color: '#c4b5fd', lineHeight: 1.6, minHeight: 48 }}>
            What were the key risks from our Q3 report, and how should we address them in Q4 planning?<span className="cursor"/>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <span style={{ fontSize: 10, color: '#2a2a3e', padding: '3px 8px', border: '1px solid var(--border)', borderRadius: 4 }}>📎</span>
            <span style={{ fontSize: 10, color: '#374151', fontFamily: 'monospace', border: '1px solid var(--border)', padding: '3px 8px', borderRadius: 4 }}>claude-sonnet-4-6 ▾</span>
            <div style={{ width: 28, height: 28, borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,var(--pink),var(--violet))', display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: 'auto' }}>{SEND_BTN_ICON}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Panel 1: Process (animated) ─────────────────────────────────────────────
function Panel1({ active }: { active: boolean }) {
  const rowRef     = React.useRef<HTMLDivElement>(null)
  const thinkRef   = React.useRef<HTMLDivElement>(null)
  const respRef    = React.useRef<HTMLDivElement>(null)
  const txtRef     = React.useRef<HTMLDivElement>(null)
  const labelRef   = React.useRef<HTMLSpanElement>(null)
  const jobRef     = React.useRef<AbortController | null>(null)

  React.useEffect(() => {
    if (!active) {
      jobRef.current?.abort()
      jobRef.current = null
      return
    }
    if (!rowRef.current || !thinkRef.current || !respRef.current || !txtRef.current || !labelRef.current) return
    const ac = new AbortController()
    jobRef.current = ac
    const refs: ChipDemoRefs = {
      row:      rowRef.current,
      thinkRow: thinkRef.current,
      respEl:   respRef.current,
      txtEl:    txtRef.current,
      labelEl:  labelRef.current,
    }
    runChipDemo(refs, ac.signal)
    return () => { ac.abort(); jobRef.current = null }
  }, [active])

  const AI_AVATAR_SVG = `<svg viewBox="0 0 80 80" fill="none" width="14" height="14"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="white" stroke-width="5"/></svg>`

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      {/* Demo left */}
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        {/* Inline demo bar with ref for label */}
        <div style={{ background: '#0c0c1a', padding: '9px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 5 }}>
          {[0,1,2].map(i => <div key={i} style={{ width: 7, height: 7, borderRadius: '50%', background: '#2a2a3e' }}/>)}
          <span ref={labelRef} style={{ fontSize: 10, color: '#2a2a3e', marginLeft: 8, fontFamily: 'monospace' }}>vortex · waiting…</span>
        </div>
        <div style={{ padding: 16 }}>
          <div className="msg-user" style={{ marginBottom: 14 }}>
            <div className="msg-user-bubble">What were the key risks from Q3, and how should we address them in Q4?</div>
          </div>
          <div ref={rowRef} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}/>
          <div ref={thinkRef} style={{ display: 'none', alignItems: 'center', gap: 5, padding: '8px 12px' }}>
            <div className="thinking-dot"/>
            <div className="thinking-dot" style={{ animationDelay: '.18s' }}/>
            <div className="thinking-dot" style={{ animationDelay: '.36s' }}/>
          </div>
          <div ref={respRef} className="msg-ai" style={{ display: 'none' }}>
            <div className="msg-ai-avatar" dangerouslySetInnerHTML={{ __html: AI_AVATAR_SVG }}/>
            <div style={{ flex: 1 }}>
              <div className="msg-ai-name">Vortex · claude-sonnet-4-6</div>
              <div ref={txtRef} className="msg-ai-text"/>
            </div>
          </div>
        </div>
      </div>
      {/* Text right */}
      <StepText
        n="2" tag="Process"
        title={<>Memories, knowledge,<br/><span style={{ color: 'var(--violet)' }}>web — all at once.</span></>}
        desc="Before responding, Vortex loads your memories, searches your knowledge base, and optionally searches the web. You see every tool call as it runs — live."
        bullets={['Memory chip loads your personal context','KB search retrieves relevant document chunks','Web search fetches live data when needed','Each chip expands to show sources']}
      />
    </div>
  )
}

// ─── Panel 2: Knowledge ───────────────────────────────────────────────────────
function Panel2() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      <StepText
        n="3" tag="Knowledge"
        title={<>Grounded answers,<br/><span style={{ color: 'var(--violet)' }}>not hallucinations.</span></>}
        desc="Attach knowledge bases to any conversation. Vortex retrieves the most relevant chunks from your documents and cites them — so every answer is traceable."
        bullets={['Unlimited knowledge base size','Semantic search across all documents','Sources shown inline below response']}
      />
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label="knowledge bases · 2 active"/>
        <div style={{ padding: 16 }}>
          <div className="chip chip-kb" style={{ marginBottom: 10, cursor: 'pointer', display: 'inline-flex' }}>
            {libIcon(12)} KB Searched "Q3 risks Q4 planning" {CHECK_ICON} {CHEV_DOWN}
          </div>
          <div style={{ padding: 10, background: '#0a0a18', border: '1px solid rgba(126,34,206,.2)', borderRadius: 8, marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(126,34,206,.6)', marginBottom: 6 }}>Sources</div>
            <div style={{ fontSize: 11, color: '#c4b5fd', marginBottom: 4 }}>Finance Docs <span style={{ color: 'rgba(167,139,250,.4)' }}>· 3 chunks</span></div>
            <div style={{ fontSize: 11, color: '#c4b5fd' }}>Q4 Planning Brief <span style={{ color: 'rgba(167,139,250,.4)' }}>· 1 chunk</span></div>
          </div>
          <div style={{ background: '#0a0a18', border: '1px solid rgba(126,34,206,.2)', borderRadius: 8, padding: 10 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(126,34,206,.6)', marginBottom: 8 }}>Used knowledge bases</div>
            {[['Finance Docs','3 chunks'],['Q4 Planning Brief','1 chunk']].map(([name, count]) => (
              <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', background: 'rgba(59,7,100,.2)', borderRadius: 6, marginBottom: 6 }}>
                {libIcon(12)}<span style={{ fontSize: 11, color: '#c4b5fd' }}>{name}</span>
                <span style={{ fontSize: 10, color: 'rgba(167,139,250,.4)', marginLeft: 'auto' }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Panel 3: Memory ─────────────────────────────────────────────────────────
function Panel3() {
  const MEMORIES = [
    { color: '#f472b6', label: 'preference', text: 'Prefers risk analysis as: problem → window → action. No bullet points.' },
    { color: '#a78bfa', label: 'context',    text: 'Head of Product at Acme Corp. Q4 planning cycle, board deck due Dec 15.', badge: true },
    { color: '#60a5fa', label: 'tools',      text: 'Linear, Notion, Figma daily. Comfortable with Python and SQL.' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center', padding: '64px 56px', animation: 'panelIn .4s ease both' }}>
      <div style={{ background: '#060610', border: '1px solid rgba(167,139,250,.1)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
        <DemoBar label="memories · 3 loaded this session"/>
        <div style={{ padding: 16 }}>
          <div className="chip chip-memory" style={{ marginBottom: 12, display: 'inline-flex' }}>
            {brainIcon(12)} 3 memories loaded {CHECK_ICON}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {MEMORIES.map(m => (
              <div key={m.label} style={{ background: '#0a0a18', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px', borderLeft: `2px solid ${m.color}` }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: m.color, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {m.label}
                  {m.badge && <span style={{ fontSize: 9, padding: '1px 5px', background: 'rgba(34,197,94,.1)', border: '1px solid rgba(34,197,94,.2)', color: '#22c55e', borderRadius: 3, textTransform: 'none', letterSpacing: 0 }}>● new</span>}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.5 }}>{m.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <StepText
        n="4" tag="Memory"
        title={<>Never repeat<br/><span style={{ color: 'var(--pink)' }}>yourself again.</span></>}
        desc="Vortex auto-learns from every conversation — your role, preferences, team context. The next session starts where the last one left off. No setup needed."
        bullets={['Auto-learned from conversation history','Manually editable, pause or delete anytime','Injected automatically into every thread']}
      />
    </div>
  )
}

// ─── Main HowItWorks component ────────────────────────────────────────────────
export function HowItWorks() {
  const [activeTab, setActiveTab] = React.useState(0)
  const sectionRef  = React.useRef<HTMLElement>(null)
  const timerRef    = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const startedRef  = React.useRef(false)
  const fillRefs    = [
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
  ]

  const activateTab = React.useCallback((idx: number) => {
    // Reset all progress bars
    fillRefs.forEach(ref => {
      if (!ref.current) return
      ref.current.style.transition = 'none'
      ref.current.style.width = '0%'
    })
    // Animate active fill
    const fill = fillRefs[idx].current
    if (fill) {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        fill.style.transition = `width ${TAB_DURATIONS[idx]}ms linear`
        fill.style.width = '100%'
      }))
    }
    setActiveTab(idx)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => activateTab((idx + 1) % 4), TAB_DURATIONS[idx])
  }, [])

  React.useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !startedRef.current) {
        startedRef.current = true
        obs.unobserve(el)
        activateTab(0)
      }
    }, { threshold: 0.25 })
    obs.observe(el)
    return () => {
      obs.disconnect()
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [activateTab])

  const panels = [<Panel0/>, <Panel1 active={activeTab === 1}/>, <Panel2/>, <Panel3/>]

  return (
    <section ref={sectionRef} id="hiw" style={{ padding: '100px 56px', background: 'var(--bg2)', borderTop: '1px solid var(--border)' }}>
      {/* Header */}
      <div style={{ maxWidth: 600, margin: '0 auto 64px', textAlign: 'center' }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--violet)', marginBottom: 12 }}>How Vortex works</div>
        <h2 style={{ fontSize: 'clamp(28px,4vw,48px)', fontWeight: 800, letterSpacing: '-.04em', lineHeight: 1.1, marginBottom: 14 }}>Your AI gets smarter<br/>every conversation</h2>
        <p style={{ fontSize: 17, color: 'var(--muted)', lineHeight: 1.7 }}>From the moment you ask to the answer that lands — Vortex works across four layers.</p>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', maxWidth: 1100, margin: '0 auto', border: '1px solid var(--border)', borderRadius: '14px 14px 0 0', overflow: 'hidden' }}>
        {TABS.map((t, i) => (
          <button
            key={t.label}
            onClick={() => { if (timerRef.current) clearTimeout(timerRef.current); activateTab(i) }}
            style={{
              position: 'relative', padding: '18px 20px 16px',
              background: activeTab === i ? 'rgba(167,139,250,.05)' : 'transparent',
              border: 'none', borderRight: i < 3 ? '1px solid var(--border)' : 'none',
              cursor: 'pointer', textAlign: 'left', overflow: 'hidden',
              color: activeTab === i ? 'var(--text)' : 'var(--muted)',
              transition: 'background .2s, color .2s',
            }}
          >
            <span style={{ display: 'block', fontSize: 10, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', fontFamily: 'monospace', color: activeTab === i ? 'var(--violet)' : 'var(--dim)', marginBottom: 4 }}>{t.step}</span>
            <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{t.label}</span>
            <span style={{ display: 'block', fontSize: 11, color: activeTab === i ? '#4b5563' : 'var(--dim)', marginTop: 3 }}>{t.sub}</span>
            {/* Progress bar */}
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 2, background: 'var(--border)' }}>
              <div ref={fillRefs[i]} style={{ height: '100%', background: 'linear-gradient(90deg,var(--violet),var(--pink))', width: '0%' }}/>
            </div>
          </button>
        ))}
      </div>

      {/* Panels */}
      <div style={{ maxWidth: 1100, margin: '0 auto', border: '1px solid var(--border)', borderTop: 'none', borderRadius: '0 0 14px 14px', overflow: 'hidden', background: '#050509' }}>
        {panels[activeTab]}
      </div>
    </section>
  )
}
