// landing/src/components/HeroSection.tsx — Landing v2 design
import * as React from 'react'
import { getAppUrl } from '~/lib/app-url'

/* ── Inline SVG helpers ─────────────────────────────────────────── */
function PrismSVG({ size = 80, id = 'pgHero', animate = 'idle' }: { size?: number; id?: string; animate?: 'idle' | 'loading' | 'streaming' }) {
  return (
    <svg viewBox="0 0 80 80" width={size} height={size}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f472b6"/>
          <stop offset="50%" stopColor="#a78bfa"/>
          <stop offset="100%" stopColor="#60a5fa"/>
        </linearGradient>
      </defs>
      <g
        className="pbox"
        style={{
          transformOrigin: '40px 40px',
          animation: animate === 'idle' ? 'prismIdleSway 4s ease-in-out infinite'
                   : animate === 'loading' ? 'prismSpin 1.2s linear infinite'
                   : 'prismPendulum 1.8s ease-in-out infinite',
        }}
      >
        <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={`url(#${id})`} strokeWidth="2.5" strokeLinejoin="round"/>
        <line x1="40" y1="8" x2="68" y2="40" stroke="#f472b6" strokeWidth="1.5" opacity="0.6"/>
        <line x1="40" y1="8" x2="40" y2="72" stroke="#a78bfa" strokeWidth="1.5" opacity="0.6"/>
        <line x1="40" y1="8" x2="12" y2="40" stroke="#60a5fa" strokeWidth="1.5" opacity="0.6"/>
        <circle cx="40" cy="40" r="4" fill="#e0d7ff"/>
      </g>
    </svg>
  )
}

function ChatIcon() {
  return (
    <svg className="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 3h10v7H8l-3 3v-3H3V3z"/>
    </svg>
  )
}
function KbIcon() {
  return (
    <svg className="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="3" width="10" height="10" rx="1"/>
      <line x1="3" y1="6" x2="13" y2="6"/>
    </svg>
  )
}

function prismInlineSVG() {
  return `<svg class="spin-prism" viewBox="0 0 16 16" fill="none"><polygon points="8,1 14,8 8,15 2,8" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="8" cy="8" r="1.2" fill="currentColor"/></svg>`
}

/* ── Hero Section ───────────────────────────────────────────────── */
export function HeroSection() {
  const threadRef = React.useRef<HTMLDivElement>(null)
  const inputRef  = React.useRef<HTMLTextAreaElement>(null)
  const sendRef   = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    const thread  = threadRef.current
    const input   = inputRef.current
    const sendBtn = sendRef.current
    if (!thread || !input || !sendBtn) return

    const query = "What's our Q3 pricing guidance for deals over $250k?"
    const responseText =
      "For Q3 2026, deals over $250k ARR go through Deal Desk regardless of product mix. " +
      "Standard packaging applies below that threshold, with two exceptions: multi-year terms " +
      "and any land where expansion potential exceeds 40% of current ARR. All quotes must include " +
      "the 12-month default term and quarterly true-ups."

    let stopped = false
    const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

    async function typeInto(el: HTMLTextAreaElement, text: string, perChar = 28) {
      el.value = ''
      for (let i = 0; i < text.length; i++) {
        if (stopped) return
        el.value += text[i]
        await wait(perChar + (Math.random() * 20 - 8))
      }
    }

    async function streamText(el: HTMLElement, text: string) {
      el.textContent = ''
      const caret = document.createElement('span')
      caret.className = 'caret'
      el.appendChild(caret)
      const chunks = text.split(/(\s+)/)
      for (const c of chunks) {
        for (const ch of c) {
          if (stopped) return
          caret.insertAdjacentText('beforebegin', ch)
          await wait(11 + Math.random() * 10)
        }
      }
      caret.remove()
    }

    async function run() {
      if (stopped) return
      if (!thread || !input || !sendBtn) return
      thread.innerHTML = ''
      input.value = ''

      await typeInto(input, query, 26)
      await wait(350)
      if (stopped) return

      sendBtn.classList.add('flash')
      await wait(250)
      sendBtn.classList.remove('flash')

      const userText = input.value
      input.value = ''

      const userMsg = document.createElement('div')
      userMsg.className = 'msg user'
      userMsg.innerHTML = `
        <div class="av">You</div>
        <div class="body">
          <div class="who">You · now</div>
          <div class="text">${userText}</div>
        </div>`
      thread.appendChild(userMsg)
      await wait(300)
      if (stopped) return

      // AI msg with chips
      const aiMsg = document.createElement('div')
      aiMsg.className = 'msg ai'
      aiMsg.innerHTML = `
        <div class="av">
          <svg viewBox="0 0 80 80" width="22" height="22" style="animation:prismSpin 1.2s linear infinite;transform-origin:40px 40px">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#pgNav)" stroke-width="3" stroke-linejoin="round"/>
            <circle cx="40" cy="40" r="5" fill="#e0d7ff"/>
          </svg>
        </div>
        <div class="body">
          <div class="who">Strategist · claude-sonnet-4.6 <span class="kb-ind" style="color:#22c55e;display:inline-flex;align-items:center;gap:4px;opacity:0;transition:opacity 200ms;margin-left:6px">📚 used knowledge</span></div>
          <div class="chips" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
            <span class="chip memory"><span class="spin">${prismInlineSVG()}</span><span class="check">✓</span>memory · loading</span>
            <span class="chip kb"><span class="spin">${prismInlineSVG()}</span><span class="check">✓</span>Product docs · searching</span>
          </div>
          <div class="thinking" style="display:none;"><span></span><span></span><span></span></div>
          <div class="text" style="font-size:13.5px;line-height:1.55;color:var(--text)"></div>
          <div class="kb-sources">
            <div class="lbl">📚 used knowledge bases</div>
            <div class="src"><span>Product docs · pricing-v12.md p.4</span><span class="score">0.91</span></div>
            <div class="src"><span>Product docs · packaging.md p.2</span><span class="score">0.84</span></div>
            <div class="src"><span>Sales playbook · gtm-q3.md §3</span><span class="score">0.77</span></div>
          </div>
        </div>`
      thread.appendChild(aiMsg)

      const memChip = aiMsg.querySelector('.chip.memory') as HTMLElement
      const kbChip  = aiMsg.querySelector('.chip.kb') as HTMLElement
      const think   = aiMsg.querySelector('.thinking') as HTMLElement
      const textEl  = aiMsg.querySelector('.text') as HTMLElement
      const kbInd   = aiMsg.querySelector('.kb-ind') as HTMLElement
      const sources = aiMsg.querySelector('.kb-sources') as HTMLElement
      const avSvg   = aiMsg.querySelector('.av svg') as SVGElement

      await wait(700)
      if (stopped) return
      memChip.classList.add('done')
      memChip.innerHTML = memChip.innerHTML.replace('memory · loading', 'memory · 14 facts')

      await wait(900)
      if (stopped) return
      kbChip.classList.add('done')
      kbChip.innerHTML = kbChip.innerHTML.replace('Product docs · searching', 'Product docs · 3 chunks')

      await wait(250)
      if (stopped) return
      if (avSvg) avSvg.style.animation = 'prismPendulum 1.8s ease-in-out infinite'
      think.style.display = 'inline-flex'
      await wait(900)
      if (stopped) return
      think.style.display = 'none'

      await streamText(textEl, responseText)
      if (stopped) return

      await wait(200)
      kbInd.style.opacity = '1'
      sources.classList.add('on')
      if (avSvg) avSvg.style.animation = 'prismIdleSway 4s ease-in-out infinite'

      await wait(6000)
      if (stopped) return
      run()
    }

    const t = setTimeout(run, 700)
    return () => { stopped = true; clearTimeout(t) }
  }, [])

  return (
    <section style={{
      maxWidth: 1280, margin: '0 auto',
      padding: '72px 32px 80px',
      display: 'grid',
      gridTemplateColumns: '1fr 1.05fr',
      gap: 60,
      alignItems: 'center',
    }}>
      {/* ── Left: copy ── */}
      <div>
        <div className="eyebrow" style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          fontFamily: '"JetBrains Mono", ui-monospace, monospace', fontSize: 11,
          color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.1em',
          marginBottom: 28,
          animation: 'fadeUp 700ms cubic-bezier(.2,.8,.2,1) both',
        }}>
          <span style={{ display: 'inline-block', width: 24, height: 1, background: 'var(--violet)' }}/>
          AI PORTAL · BUILT FOR TEAMS
        </div>

        <h1 style={{
          margin: '0 0 28px',
          fontSize: 72, fontWeight: 700,
          letterSpacing: '-0.035em', lineHeight: 1.0,
        }}>
          <span style={{ display: 'block', color: 'var(--text)', animation: 'fadeUp 900ms 80ms cubic-bezier(.2,.8,.2,1) both' }}>Ask anything.</span>
          <span style={{
            display: 'block',
            background: 'linear-gradient(90deg, #f472b6 0%, #a78bfa 50%, #60a5fa 100%)',
            backgroundSize: '400% 100%',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
            animation: 'fadeUp 900ms 200ms cubic-bezier(.2,.8,.2,1) both, shineSweep 4s 1000ms cubic-bezier(.2,.8,.2,1) both',
          }}>Know everything.</span>
          <span style={{ display: 'block', color: 'var(--muted)', fontWeight: 500, animation: 'fadeUp 900ms 320ms cubic-bezier(.2,.8,.2,1) both' }}>Ship faster.</span>
        </h1>

        <p style={{
          fontSize: 19, lineHeight: 1.55, color: 'var(--text-2)',
          maxWidth: 520, margin: '0 0 36px',
          animation: 'fadeUp 900ms 420ms cubic-bezier(.2,.8,.2,1) both',
        }}>
          Vortex is the AI portal your team actually wants to use. One chat for every model. Your knowledge, your memory, your guardrails — under one roof.
        </p>

        <div style={{ display: 'flex', gap: 10, marginBottom: 36, animation: 'fadeUp 900ms 520ms cubic-bezier(.2,.8,.2,1) both' }}>
          <a className="btn btn-grad" href={`${getAppUrl()}/register`}>
            <span className="inner">Start for free <span>→</span></span>
          </a>
          <a className="btn" href="#how">How it works</a>
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          fontFamily: '"JetBrains Mono", ui-monospace, monospace', fontSize: 11, color: 'var(--muted)',
          animation: 'fadeUp 900ms 620ms cubic-bezier(.2,.8,.2,1) both',
        }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: '#22c55e', boxShadow: '0 0 10px #22c55e',
            animation: 'pulse 1.8s ease-in-out infinite',
            display: 'inline-block',
          }}/>
          No credit card · Google, GitHub, or email · Self-host ready
        </div>
      </div>

      {/* ── Right: app demo frame ── */}
      <div style={{
        position: 'relative',
        height: 560, borderRadius: 14, overflow: 'hidden',
        background: 'var(--bg2)', border: '1px solid var(--border)',
        boxShadow: '0 1px 0 rgba(255,255,255,0.04) inset, 0 40px 80px -30px rgba(0,0,0,0.6), 0 0 120px -30px rgba(167,139,250,0.35)',
        animation: 'heroIn 1200ms cubic-bezier(.2,.8,.2,1) both',
      }}>
        {/* Chrome titlebar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px', borderBottom: '1px solid var(--border)',
          background: 'var(--bg2)',
        }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {[0,1,2].map(i => <span key={i} style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--b2)', display: 'inline-block' }}/>)}
          </div>
          <div style={{
            flex: 1, margin: '0 8px', height: 22, borderRadius: 5,
            background: 'var(--bg-3)', border: '1px solid var(--border)',
            padding: '0 10px', display: 'flex', alignItems: 'center',
            fontFamily: '"JetBrains Mono", monospace', fontSize: 11, color: 'var(--muted)', gap: 6,
          }}>
            <span style={{ fontSize: 9, opacity: 0.6 }}>🔒</span>
            <span style={{ color: 'var(--text-2)' }}>vortex.app</span>
            <span>/chat/c/0x9f4a…</span>
          </div>
        </div>

        {/* App body */}
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', height: 'calc(100% - 43px)' }}>
          {/* Sidebar */}
          <aside style={{
            background: 'var(--bg2)', borderRight: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column',
            padding: '12px 8px', gap: 14, overflow: 'hidden',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', fontWeight: 600, fontSize: 14, letterSpacing: '-0.01em' }}>
              <span style={{ display: 'inline-block', width: 20, height: 20 }}>
                <PrismSVG size={20} id="pgSide" animate="idle" />
              </span>
              <span style={{ background: 'var(--g-grad)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', fontWeight: 700 }}>Vortex</span>
            </div>
            <div>
              <div style={{ fontFamily: 'monospace', fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.1em', padding: '0 10px', marginBottom: 4 }}>Conversations</div>
              {[
                { label: 'Q3 go-to-market…', active: true },
                { label: 'Pricing analysis' },
                { label: 'Benchmark research' },
                { label: 'Onboarding email' },
              ].map(item => (
                <div key={item.label} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', borderRadius: 5,
                  fontSize: 12.5, color: item.active ? 'var(--text)' : 'var(--text-2)',
                  background: item.active ? 'rgba(167,139,250,0.12)' : 'transparent',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  <ChatIcon />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{ fontFamily: 'monospace', fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.1em', padding: '0 10px', marginBottom: 4 }}>Knowledge</div>
              {[
                { label: 'Product docs', badge: '284' },
                { label: 'Sales playbook', badge: '41' },
                { label: 'Engineering wiki', badge: '1.2k' },
              ].map(item => (
                <div key={item.label} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', borderRadius: 5,
                  fontSize: 12.5, color: 'var(--text-2)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  <KbIcon />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>
                  <span style={{ marginLeft: 'auto', fontFamily: 'monospace', fontSize: 10, color: 'var(--muted)', flexShrink: 0 }}>{item.badge}</span>
                </div>
              ))}
            </div>
          </aside>

          {/* Chat area */}
          <div style={{ display: 'flex', flexDirection: 'column', background: 'var(--bg)', overflow: 'hidden' }}>
            {/* Chat header */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '12px 18px', borderBottom: '1px solid var(--border)',
              background: 'var(--bg2)',
            }}>
              <div>
                <div style={{ fontWeight: 500, fontSize: 13 }}>Q3 go-to-market planning</div>
                <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)' }}>with Strategist · using Product docs + Sales playbook</div>
              </div>
              <div style={{
                marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '3px 8px', borderRadius: 5,
                fontFamily: 'monospace', fontSize: 11,
                background: 'var(--panel)', border: '1px solid var(--border)', color: 'var(--text-2)',
              }}>
                ◆ claude-sonnet-4.6
              </div>
            </div>

            {/* Thread */}
            <div
              ref={threadRef}
              style={{
                flex: 1, overflow: 'hidden',
                padding: '20px 22px',
                display: 'flex', flexDirection: 'column', gap: 16,
              }}
            />

            {/* Composer */}
            <div className="composer">
              <div className="composer-top">
                <span className="cap on reflect">
                  <svg className="ic" viewBox="0 0 10 10" fill="currentColor"><circle cx="5" cy="5" r="3"/></svg>
                  Reflection
                </span>
                <span className="cap on research">
                  <svg className="ic" viewBox="0 0 10 10" fill="currentColor"><rect x="1" y="1" width="8" height="8" rx="1"/></svg>
                  Research
                </span>
                <span className="cap">2 KBs · attached</span>
              </div>
              <div className="composer-mid">
                <textarea ref={inputRef} placeholder="Message Vortex…" rows={1} readOnly />
                <button ref={sendRef} className="send" aria-label="Send">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M1 8l14-7-5 15-3-6-6-2z"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
