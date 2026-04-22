// landing/src/components/HowItWorks.tsx — Landing v2 design
import * as React from 'react'

const TAB_DURATIONS = [5000, 11000, 5000, 5000]

const TABS = [
  { num: '01 · COMPOSE',  label: 'Any model. Any capability.', desc: 'Pick a model. Flip Research or Reflection. Attach a KB.' },
  { num: '02 · PROCESS',  label: 'Watch it think.',            desc: 'Memory, knowledge, and tools run live — in plain sight.' },
  { num: '03 · KNOWLEDGE',label: 'Grounded answers.',          desc: 'Semantic search over your docs. Every claim, cited.' },
  { num: '04 · MEMORY',   label: 'Remembers what matters.',    desc: 'Preferences, context, tools — learned across threads.' },
]

/* ── Bullet list ──────────────────────────────────────────────────── */
function BulletList({ items }: { items: string[] }) {
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: '16px 0 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map((item, i) => (
        <li key={i} style={{ display: 'flex', gap: 10, fontSize: 13.5, color: 'var(--text-2)', alignItems: 'flex-start' }}>
          <span style={{
            flexShrink: 0, width: 18, height: 18, marginTop: 1,
            borderRadius: '50%',
            background: 'rgba(167,139,250,0.15)',
            border: '1px solid rgba(167,139,250,0.4)',
            backgroundImage: 'radial-gradient(circle, var(--violet) 30%, transparent 35%)',
            display: 'inline-block',
          }}/>
          {item}
        </li>
      ))}
    </ul>
  )
}

/* ── Tab 0: Compose ───────────────────────────────────────────────── */
function Panel0() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 40, alignItems: 'center' }} className="tab-panel active">
      <div className="copy">
        <h3 style={{ margin: '0 0 14px', fontSize: 28, fontWeight: 600, letterSpacing: '-0.02em' }}>Compose with every capability.</h3>
        <p style={{ margin: '0 0 16px', color: 'var(--text-2)', fontSize: 15, lineHeight: 1.55 }}>
          One composer, every lever. Pick any model. Flip <strong>Research</strong> for live web search. Flip <strong>Reflection</strong> for extended thinking. Attach a knowledge base and the model grounds against your docs — without leaving the thread.
        </p>
        <BulletList items={[
          'Every major provider — Anthropic, OpenAI, Google, Mistral, open-source.',
          'Capabilities as toggles: Research, Reflection, Vision, Code Interpreter.',
          'KBs attach per-conversation. No global index-swapping roulette.',
        ]}/>
      </div>
      <div style={{ borderRadius: 12, background: 'var(--bg2)', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 30px 60px -30px rgba(0,0,0,0.6)', minHeight: 380 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-3)', fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 8 }}>
          ◆ composer · new message
        </div>
        <div style={{ padding: 28 }}>
          <div className="composer" style={{ margin: 0 }}>
            <div className="composer-top">
              <span className="cap on reflect"><svg className="ic" viewBox="0 0 10 10" fill="currentColor"><circle cx="5" cy="5" r="3"/></svg>Reflection</span>
              <span className="cap on research"><svg className="ic" viewBox="0 0 10 10" fill="currentColor"><rect x="1" y="1" width="8" height="8" rx="1"/></svg>Research</span>
              <span className="cap">◆ claude-sonnet-4.6</span>
              <span className="cap">Product docs + 1</span>
            </div>
            <div className="composer-mid">
              <textarea placeholder="Message Vortex…" rows={3} readOnly/>
              <button className="send" aria-label="Send">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M1 8l14-7-5 15-3-6-6-2z"/></svg>
              </button>
            </div>
          </div>
          <div style={{ marginTop: 14, fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)', display: 'flex', gap: 14 }}>
            {[['↵', 'Send'], ['⇧↵', 'New line'], ['⌘K', 'Model'], ['@', 'Attach KB']].map(([key, label]) => (
              <span key={key}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px', borderRadius: 4, background: 'var(--panel)', border: '1px solid var(--b2)', fontSize: 10 }}>{key}</span>
                {' '}{label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Tab 1: Process (animated) ────────────────────────────────────── */
function Panel1({ active }: { active: boolean }) {
  const threadRef = React.useRef<HTMLDivElement>(null)
  const abortRef  = React.useRef<AbortController | null>(null)

  React.useEffect(() => {
    if (!active) {
      abortRef.current?.abort()
      abortRef.current = null
      return
    }
    const ac = new AbortController()
    abortRef.current = ac
    const signal = ac.signal

    const wait = (ms: number) => new Promise<void>((res, rej) => {
      const t = setTimeout(res, ms)
      signal.addEventListener('abort', () => { clearTimeout(t); rej(new Error('aborted')) }, { once: true })
    })

    async function run() {
      const thread = threadRef.current
      if (!thread) return
      thread.innerHTML = ''
      try {
        const um = document.createElement('div')
        um.className = 'msg user'
        um.innerHTML = `
          <div class="av">You</div>
          <div class="body">
            <div class="who">You · now</div>
            <div class="text">Summarize the Q3 pricing guardrails for a deal over $250k.</div>
          </div>`
        thread.appendChild(um)
        await wait(400)

        const ai = document.createElement('div')
        ai.className = 'msg ai'
        ai.innerHTML = `
          <div class="av">
            <span class="prism loading" style="width:22px;height:22px;display:inline-block;color:#a78bfa;">
              <svg viewBox="0 0 80 80" width="22" height="22">
                <g class="pbox">
                  <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#pgNav)" stroke-width="3" stroke-linejoin="round"/>
                  <circle cx="40" cy="40" r="5" fill="#e0d7ff"/>
                </g>
              </svg>
            </span>
          </div>
          <div class="body">
            <div class="who"><span>Claude · now</span></div>
            <div class="think-block">
              <div class="think-head">
                <span class="pulse"></span>
                <span class="lbl">Thinking</span>
                <span class="meta" data-meta>running</span>
                <svg class="caret-ic" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="2,4 5,7 8,4"/></svg>
              </div>
              <div class="think-body">
                <div class="tool-card memory" data-tool="memory">
                  <div class="ic-box">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 13c-3 0-5-2-5-4.5S5 4 8 4s5 2 5 4.5S11 13 8 13z"/><path d="M5 8.5c0-1 .8-1.5 1.5-1.5M11 8.5c0-1-.8-1.5-1.5-1.5"/></svg>
                  </div>
                  <span class="tool-name">recall_memory</span>
                  <span class="tool-arg">query: "pricing guardrails"</span>
                  <span class="tool-status"><span class="spinner"></span><span class="ok"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="2,5 4,7 8,3"/></svg>14 facts</span></span>
                </div>
                <div class="tool-card kb" data-tool="kb">
                  <div class="ic-box">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5v9a.5.5 0 0 1-.8.4L8 10.6 3.8 12.9a.5.5 0 0 1-.8-.4v-9z"/></svg>
                  </div>
                  <span class="tool-name">search_knowledge_base</span>
                  <span class="tool-arg">kb: Sales playbook · top_k=8</span>
                  <span class="tool-status"><span class="spinner"></span><span class="ok"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="2,5 4,7 8,3"/></svg>3 chunks · 0.89</span></span>
                </div>
                <div class="tool-card web" data-tool="web">
                  <div class="ic-box">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><line x1="2" y1="8" x2="14" y2="8"/><path d="M8 2c2 2 3 4 3 6s-1 4-3 6c-2-2-3-4-3-6s1-4 3-6z"/></svg>
                  </div>
                  <span class="tool-name">web_search</span>
                  <span class="tool-arg">"SaaS Q3 2026 pricing benchmark"</span>
                  <span class="tool-status"><span class="spinner"></span><span class="ok"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="2,5 4,7 8,3"/></svg>2 results</span></span>
                </div>
              </div>
            </div>
            <div class="thinking" style="display:none;"><span></span><span></span><span></span></div>
            <div class="text"></div>
          </div>`
        thread.appendChild(ai)

        const thinkBlock = ai.querySelector('.think-block') as HTMLElement
        const thinkMeta  = ai.querySelector('[data-meta]') as HTMLElement
        const memCard    = ai.querySelector('[data-tool="memory"]') as HTMLElement
        const kbCard     = ai.querySelector('[data-tool="kb"]') as HTMLElement
        const webCard    = ai.querySelector('[data-tool="web"]') as HTMLElement
        const think      = ai.querySelector('.thinking') as HTMLElement
        const textEl     = ai.querySelector('.text') as HTMLElement
        const prism      = ai.querySelector('.prism') as HTMLElement

        await wait(700)
        memCard.classList.add('done')

        await wait(700)
        kbCard.classList.add('done')

        await wait(600)
        webCard.classList.add('done')

        await wait(200)
        prism.classList.remove('loading')
        prism.classList.add('streaming')
        think.style.display = 'inline-flex'
        await wait(900)
        think.style.display = 'none'

        const txt = "For any Q3 deal over $250k ARR, route to Deal Desk regardless of product mix. The standard packaging tier applies below that line, with two carve-outs: multi-year terms and land expansions above 40%. Always include 12-month default term and quarterly true-ups."
        textEl.textContent = ''
        const caret = document.createElement('span')
        caret.className = 'caret'
        textEl.appendChild(caret)
        for (const ch of txt) {
          if (signal.aborted) throw new Error('aborted')
          caret.insertAdjacentText('beforebegin', ch)
          await wait(11 + Math.random() * 10)
        }
        caret.remove()
        thinkBlock.classList.add('done', 'collapsed')
        thinkMeta.textContent = '3 tools · 2.1s'
        prism.classList.remove('streaming')
        prism.classList.add('idle')
      } catch {
        /* aborted */
      }
    }

    run()
    return () => { ac.abort() }
  }, [active])

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 40, alignItems: 'center' }}>
      <div className="copy">
        <h3 style={{ margin: '0 0 14px', fontSize: 28, fontWeight: 600, letterSpacing: '-0.02em' }}>Every hop, visible.</h3>
        <p style={{ margin: '0 0 16px', color: 'var(--text-2)', fontSize: 15, lineHeight: 1.55 }}>
          When Vortex thinks, you see it. Memory lookups, knowledge-base retrievals, web searches, tool calls — each surfaces as a live chip with status. No black boxes, no fake "typing" lag.
        </p>
        <BulletList items={[
          'Memory pulls in what the model already knows about you.',
          'KB search runs hybrid BM25 + vector + rerank.',
          'Web search opens a live browser. Tool calls show schema.',
        ]}/>
      </div>
      <div style={{ borderRadius: 12, background: 'var(--bg2)', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 30px 60px -30px rgba(0,0,0,0.6)', minHeight: 380 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-3)', fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)' }}>
          ◆ thread · process demo
        </div>
        <div ref={threadRef} style={{ padding: '20px 22px', minHeight: 320, display: 'flex', flexDirection: 'column', gap: 16 }}/>
      </div>
    </div>
  )
}

/* ── Tab 2: Knowledge ─────────────────────────────────────────────── */
function Panel2() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 40, alignItems: 'center' }}>
      <div className="copy">
        <h3 style={{ margin: '0 0 14px', fontSize: 28, fontWeight: 600, letterSpacing: '-0.02em' }}>Answers grounded in your docs.</h3>
        <p style={{ margin: '0 0 16px', color: 'var(--text-2)', fontSize: 15, lineHeight: 1.55 }}>
          Attach any knowledge base and Vortex grounds against it. Every answer that used retrieval shows a green 📚 — hover to see which KB, which chunks, which score.
        </p>
        <BulletList items={[
          'Hybrid search: BM25 + pgvector + rerank.',
          'Citations inline. Source panel on every AI turn.',
          'Upload once; incremental re-index keeps it fresh.',
        ]}/>
      </div>
      <div style={{ borderRadius: 12, background: 'var(--bg2)', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 30px 60px -30px rgba(0,0,0,0.6)', minHeight: 380 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-3)', fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)' }}>
          ◆ sources panel · last response
        </div>
        <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* KB chip full width */}
          <div style={{
            gridColumn: '1 / -1',
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '10px 14px', borderRadius: 10,
            border: '1px solid rgba(126,34,206,0.4)',
            background: 'rgba(59,7,100,0.2)',
            color: '#c4b5fd', fontSize: 13,
          }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="12" height="11" rx="1"/><line x1="2" y1="6" x2="14" y2="6"/></svg>
            <span style={{ fontWeight: 500, color: 'var(--text)' }}>Product docs</span>
            <span>· 3 chunks used</span>
            <span style={{ marginLeft: 'auto', fontFamily: 'monospace', fontSize: 11 }}>top score 0.91</span>
          </div>
          {/* Source cards */}
          {[
            { title: 'Pricing model — Enterprise tiers', meta: 'pricing-v12.md · p.4', snip: 'Enterprise tier is billed on monthly active agents, not on per-token usage. The effective cost scales sub-linearly above 25 seats…', score: '0.91' },
            { title: 'Packaging FAQ', meta: 'packaging.md · p.2', snip: 'For deal sizes over $250k ARR the Deal Desk review is required; for land expansions under 20% the standard pricing card applies…', score: '0.84' },
          ].map(src => (
            <div key={src.title} style={{ padding: 14, borderRadius: 8, background: 'var(--panel)', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>{src.title}</div>
              <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)' }}>{src.meta}</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 8, lineHeight: 1.5 }}>{src.snip}</div>
              <span style={{ display: 'inline-block', marginTop: 8, fontFamily: 'monospace', fontSize: 10, padding: '2px 6px', borderRadius: 3, background: 'rgba(167,139,250,0.15)', color: 'var(--violet)' }}>{src.score}</span>
            </div>
          ))}
          <div style={{ gridColumn: '1 / -1', padding: 14, borderRadius: 8, background: 'var(--panel)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>GTM Playbook — Q3 2026</div>
            <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)' }}>gtm-q3.md · §3 "Pricing guardrails"</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 8, lineHeight: 1.5 }}>All Q3 quotes must include the standard 12-month term with quarterly true-up. Multi-year deals route to Deal Desk regardless of size.</div>
            <span style={{ display: 'inline-block', marginTop: 8, fontFamily: 'monospace', fontSize: 10, padding: '2px 6px', borderRadius: 3, background: 'rgba(167,139,250,0.15)', color: 'var(--violet)' }}>0.77</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Tab 3: Memory ────────────────────────────────────────────────── */
function Panel3() {
  const MEMORIES = [
    { type: 'preference', color: 'var(--pink)',   text: 'Prefers concise answers with bullet points over prose.', meta: 'source: auto · 4 days ago · used in 12 threads' },
    { type: 'context',    color: 'var(--violet)', text: 'Leads GTM strategy at an AI infrastructure company (Series B).', meta: 'source: auto · 2 weeks ago · used in 38 threads' },
    { type: 'tools',      color: 'var(--blue)',   text: 'Works primarily in Notion and Linear. Exports to PDF via Granola.', meta: 'source: manual · 1 month ago · used in 9 threads' },
    { type: 'preference', color: 'var(--pink)',   text: 'Wants all pricing discussions to cite the Q3 GTM playbook.', meta: 'source: manual · 2 days ago · used in 3 threads' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 40, alignItems: 'center' }}>
      <div className="copy">
        <h3 style={{ margin: '0 0 14px', fontSize: 28, fontWeight: 600, letterSpacing: '-0.02em' }}>Context that follows you.</h3>
        <p style={{ margin: '0 0 16px', color: 'var(--text-2)', fontSize: 15, lineHeight: 1.55 }}>
          Vortex learns what you prefer, what you work on, and what tools you use — and quietly injects the relevant bits into every thread. Edit, toggle, or delete any memory. You're always in control.
        </p>
        <BulletList items={[
          'Auto-extracted after each turn. No prompt stuffing.',
          'Scoped: preferences, context, tools — color-coded.',
          'Manual memories work the same. All editable, all auditable.',
        ]}/>
      </div>
      <div style={{ borderRadius: 12, background: 'var(--bg2)', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 30px 60px -30px rgba(0,0,0,0.6)', minHeight: 380 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-3)', fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)' }}>
          ◆ memories · 14 active
        </div>
        <div style={{ padding: 20 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            height: 24, padding: '0 10px', borderRadius: 12,
            border: '1px solid rgba(59,130,246,0.35)',
            background: 'rgba(23,37,84,0.4)',
            color: '#93c5fd',
            fontFamily: 'monospace', fontSize: 11,
            marginBottom: 14,
          }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 4h8v6H8l-2 2v-2H4V4z"/></svg>
            memory · 14 facts loaded
          </div>
          {MEMORIES.map((m, i) => (
            <div key={i} style={{
              padding: '12px 14px', borderRadius: 8,
              background: 'var(--panel)', border: '1px solid var(--border)',
              borderLeftWidth: 3, borderLeftColor: m.color,
              marginBottom: 8,
              display: 'grid', gridTemplateColumns: '1fr auto', gap: 12,
              alignItems: 'center',
            }}>
              <div style={{ fontSize: 13, color: 'var(--text)' }}>{m.text}</div>
              <span style={{
                fontFamily: 'monospace', fontSize: 10,
                textTransform: 'uppercase', letterSpacing: '0.06em',
                padding: '2px 6px', borderRadius: 3,
                background: 'var(--bg-3)', color: 'var(--muted)',
              }}>{m.type}</span>
              <div style={{ gridColumn: '1 / -1', fontFamily: 'monospace', fontSize: 10.5, color: 'var(--muted)' }}>{m.meta}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Main HowItWorks ──────────────────────────────────────────────── */
export function HowItWorks() {
  const [activeTab, setActiveTab] = React.useState(0)
  const sectionRef  = React.useRef<HTMLElement>(null)
  const startedRef  = React.useRef(false)
  const timerRef    = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const rafRef      = React.useRef<number | null>(null)
  const t0Ref       = React.useRef<number>(0)
  const fillRefs    = [
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
    React.useRef<HTMLDivElement>(null),
  ]

  const activateTab = React.useCallback((idx: number) => {
    // Reset all fills
    fillRefs.forEach(ref => {
      if (!ref.current) return
      ref.current.style.transition = 'none'
      ref.current.style.width = '0%'
    })
    setActiveTab(idx)
    if (timerRef.current) clearTimeout(timerRef.current)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)

    const dur = TAB_DURATIONS[idx]
    const fill = fillRefs[idx].current
    if (!fill) return

    t0Ref.current = performance.now()
    const loop = (t: number) => {
      const k = Math.min(1, (t - t0Ref.current) / dur)
      fill.style.width = `${k * 100}%`
      if (k < 1) {
        rafRef.current = requestAnimationFrame(loop)
      } else {
        activateTab((idx + 1) % TABS.length)
      }
    }
    rafRef.current = requestAnimationFrame(loop)
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
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [activateTab])

  const panels = [<Panel0 key="0"/>, <Panel1 key="1" active={activeTab === 1}/>, <Panel2 key="2"/>, <Panel3 key="3"/>]

  return (
    <section ref={sectionRef} id="how" style={{ maxWidth: 1280, margin: '0 auto', padding: '120px 32px' }}>
      {/* Header */}
      <div className="section-head reveal">
        <div className="k">How it works</div>
        <h2>
          One portal.{' '}
          <em className="em">Every model.</em>
          <br/>All your context.
        </h2>
        <p className="sub">
          Vortex is a chat — with the memory, the retrieval, and the guardrails a team needs. Pick a model, attach a knowledge base, and ship.
        </p>
      </div>

      {/* Tab bar */}
      <div className="reveal" style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 2,
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
        marginBottom: 40,
      }}>
        {TABS.map((t, i) => (
          <button
            key={t.label}
            onClick={() => {
              if (rafRef.current) cancelAnimationFrame(rafRef.current)
              activateTab(i)
            }}
            style={{
              position: 'relative', padding: '22px 22px 24px',
              background: activeTab === i ? 'rgba(167,139,250,0.06)' : 'transparent',
              border: 'none', borderRight: i < 3 ? '1px solid var(--border)' : 'none',
              cursor: 'pointer', textAlign: 'left', overflow: 'hidden',
              transition: 'background 200ms',
            }}
          >
            <div style={{ fontFamily: 'monospace', fontSize: 11, color: activeTab === i ? 'var(--violet)' : 'var(--muted)', letterSpacing: '0.1em' }}>{t.num}</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4, letterSpacing: '-0.01em', color: activeTab === i ? 'var(--text)' : 'var(--text-2)' }}>{t.label}</div>
            <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4, lineHeight: 1.4 }}>{t.desc}</div>
            {/* Progress bar */}
            <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 2, background: 'var(--bg2)' }}>
              <div ref={fillRefs[i]} style={{ height: '100%', width: 0, background: 'var(--g-grad)' }}/>
            </div>
          </button>
        ))}
      </div>

      {/* Panel stage */}
      <div style={{ minHeight: 440, position: 'relative', animation: 'panelIn 500ms cubic-bezier(.2,.8,.2,1) both' }}>
        {panels[activeTab]}
      </div>
    </section>
  )
}
