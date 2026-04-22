// landing/src/components/HeroSection.tsx — Landing v2 design
import * as React from 'react'
import { getAppUrl } from '~/lib/app-url'

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

      const aiMsg = document.createElement('div')
      aiMsg.className = 'msg ai'
      aiMsg.innerHTML = `
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
          <div class="who">
            <span>Claude · 2:14 PM</span>
            <span class="kb-ind">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3.5 2.5h7a1 1 0 0 1 1 1V13l-4.5-2.5L2.5 13V3.5a1 1 0 0 1 1-1z"/></svg>
            </span>
          </div>
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
                <span class="tool-arg">query: "Q3 pricing"</span>
                <span class="tool-status"><span class="spinner"></span><span class="ok"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="2,5 4,7 8,3"/></svg>14 facts</span></span>
              </div>
              <div class="tool-card kb" data-tool="kb">
                <div class="ic-box">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5v9a.5.5 0 0 1-.8.4L8 10.6 3.8 12.9a.5.5 0 0 1-.8-.4v-9z"/></svg>
                </div>
                <span class="tool-name">search_knowledge_base</span>
                <span class="tool-arg">2 KBs</span>
                <span class="tool-status"><span class="spinner"></span><span class="ok"><svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2"><polyline points="2,5 4,7 8,3"/></svg>3 chunks · 0.91</span></span>
              </div>
            </div>
          </div>
          <div class="thinking" style="display:none;"><span></span><span></span><span></span></div>
          <div class="text" style="font-size:13.5px;line-height:1.55;color:var(--text)"></div>
          <div class="kb-sources">
            <div class="lbl">Sources</div>
            <div class="src"><span>Product docs · pricing-v12.md · §Deal Desk</span><span class="score">0.91</span></div>
            <div class="src"><span>Product docs · packaging.md · §Tiers</span><span class="score">0.84</span></div>
            <div class="src"><span>Sales playbook · gtm-q3.md · §3 Carve-outs</span><span class="score">0.77</span></div>
          </div>
        </div>`
      thread.appendChild(aiMsg)

      const thinkBlock = aiMsg.querySelector('.think-block') as HTMLElement
      const thinkMeta  = aiMsg.querySelector('[data-meta]') as HTMLElement
      const memCard    = aiMsg.querySelector('[data-tool="memory"]') as HTMLElement
      const kbCard     = aiMsg.querySelector('[data-tool="kb"]') as HTMLElement
      const think      = aiMsg.querySelector('.thinking') as HTMLElement
      const textEl     = aiMsg.querySelector('.text') as HTMLElement
      const kbInd      = aiMsg.querySelector('.kb-ind') as HTMLElement
      const sources    = aiMsg.querySelector('.kb-sources') as HTMLElement
      const prism      = aiMsg.querySelector('.prism') as HTMLElement

      await wait(700)
      if (stopped) return
      memCard.classList.add('done')

      await wait(900)
      if (stopped) return
      kbCard.classList.add('done')

      await wait(250)
      if (stopped) return
      prism.classList.remove('loading')
      prism.classList.add('streaming')
      think.style.display = 'inline-flex'
      await wait(900)
      if (stopped) return
      think.style.display = 'none'

      await streamText(textEl, responseText)
      if (stopped) return

      await wait(200)
      kbInd.classList.add('on')
      sources.classList.add('on')
      thinkBlock.classList.add('done', 'collapsed')
      thinkMeta.textContent = '2 tools · 1.8s'
      prism.classList.remove('streaming')
      prism.classList.add('idle')

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
      gridTemplateColumns: '1fr 1.3fr',
      gap: 40,
      alignItems: 'center',
    }}>
      {/* ── Left: copy ── */}
      <div>
        <div className="eyebrow">AI PORTAL · BUILT FOR TEAMS</div>

        <h1 style={{
          margin: '0 0 28px',
          fontSize: 72, fontWeight: 700,
          letterSpacing: '-0.035em', lineHeight: 1.0,
        }}>
          <span className="l1" style={{ display: 'block', color: 'var(--text)', animation: 'fadeUp 900ms 80ms cubic-bezier(.2,.8,.2,1) both' }}>Ask anything.</span>
          <span className="l2" style={{
            display: 'block',
            background: 'linear-gradient(90deg, #f472b6 0%, #a78bfa 50%, #60a5fa 100%)',
            backgroundSize: '400% 100%',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
            animation: 'fadeUp 900ms 200ms cubic-bezier(.2,.8,.2,1) both, shineSweep 4s 1000ms cubic-bezier(.2,.8,.2,1) both',
          }}>Know everything.</span>
          <span className="l3" style={{ display: 'block', color: 'var(--muted)', fontWeight: 500, animation: 'fadeUp 900ms 320ms cubic-bezier(.2,.8,.2,1) both' }}>Ship faster.</span>
        </h1>

        <p className="lede" style={{
          fontSize: 19, lineHeight: 1.55, color: 'var(--text-2)',
          maxWidth: 520, margin: '0 0 36px',
          animation: 'fadeUp 900ms 420ms cubic-bezier(.2,.8,.2,1) both',
        }}>
          Vortex is the AI portal your team actually wants to use. One chat for every model. Your knowledge, your memory, your guardrails — under one roof.
        </p>

        <div className="cta-row" style={{ display: 'flex', gap: 10, marginBottom: 36, animation: 'fadeUp 900ms 520ms cubic-bezier(.2,.8,.2,1) both' }}>
          <a className="btn btn-grad" href={`${getAppUrl()}/register`}>
            <span className="inner">Start for free <span className="arr">→</span></span>
          </a>
          <a className="btn" href="#how">How it works</a>
        </div>

        <div className="sub-note" style={{
          display: 'flex', alignItems: 'center', gap: 12,
          fontFamily: '"JetBrains Mono", ui-monospace, monospace', fontSize: 11, color: 'var(--muted)',
          animation: 'fadeUp 900ms 620ms cubic-bezier(.2,.8,.2,1) both',
        }}>
          <span className="dot" style={{
            width: 5, height: 5, borderRadius: '50%',
            background: '#22c55e', boxShadow: '0 0 10px #22c55e',
            animation: 'pulse 1.8s ease-in-out infinite',
            display: 'inline-block',
          }}/>
          No credit card · Google, GitHub, or email · Self-host ready
        </div>
      </div>

      {/* ── Right: app demo frame ── */}
      <div className="app-frame">
        {/* Chrome titlebar */}
        <div className="chrome">
          <div className="lights">
            <span/><span/><span/>
          </div>
          <div className="url">
            <span className="host">vortex.app</span>
            <span>/chat/c/0x9f4a…</span>
          </div>
        </div>

        {/* App body */}
        <div className="app-body">
          {/* Sidebar */}
          <aside className="side">
            <div className="side-head">
              <span className="prism idle" style={{ width: 20, height: 20, display: 'inline-block' }}>
                <svg viewBox="0 0 80 80" width="20" height="20">
                  <g className="pbox">
                    <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="url(#pgNav)" strokeWidth="3" strokeLinejoin="round"/>
                    <circle cx="40" cy="40" r="5" fill="#e0d7ff"/>
                  </g>
                </svg>
              </span>
              <span className="wm">Vortex</span>
            </div>

            <button className="side-new">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/>
              </svg>
              New conversation
              <span className="kbd">⌘K</span>
            </button>

            <div className="side-group">
              <div className="side-sect">Conversations</div>
              {[
                { label: 'Q3 pricing guardrails', active: true },
                { label: 'Deal Desk policy rewrite' },
                { label: 'Benchmark — Perplexity v Glean' },
                { label: 'Onboarding email draft' },
              ].map(item => (
                <div key={item.label} className={`side-item${item.active ? ' active' : ''}`}>
                  <svg className="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 3h10v7H8l-3 3v-3H3V3z"/>
                  </svg>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>
                </div>
              ))}
              <button className="side-more">Load older</button>
            </div>

            <div className="side-group">
              <div className="side-sect">
                Memories <span className="side-count">14</span>
              </div>
              <div className="side-item">
                <svg className="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M8 2.5c-2 0-3.5 1.5-3.5 3.5 0 .8.3 1.5.7 2.1C4.6 8.8 4 9.8 4 11c0 1.5 1.2 2.5 2.5 2.5h3c1.3 0 2.5-1 2.5-2.5 0-1.2-.6-2.2-1.2-2.9.4-.6.7-1.3.7-2.1C11.5 4 10 2.5 8 2.5z"/>
                </svg>
                <span>All memories</span>
              </div>
            </div>

            <div className="side-group">
              <div className="side-sect">Knowledge bases</div>
              {[
                { label: 'Product docs', badge: '284' },
                { label: 'Sales playbook', badge: '41' },
                { label: 'Engineering wiki', badge: '1.2k' },
                { label: 'HR policies', badge: '62' },
              ].map(item => (
                <div key={item.label} className="side-item">
                  <svg className="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 3.5A1.5 1.5 0 0 1 4.5 2h7A1.5 1.5 0 0 1 13 3.5v9a.5.5 0 0 1-.8.4L8 10.6 3.8 12.9a.5.5 0 0 1-.8-.4v-9z"/>
                  </svg>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.label}</span>
                  <span className="badge">{item.badge}</span>
                </div>
              ))}
            </div>

            <div className="side-user">
              <div className="side-avatar">RO</div>
              <div className="who-lines">
                <div className="name">Rita Okafor</div>
                <div className="tenant">northwind · entra ↗</div>
              </div>
              <svg style={{ width: 14, height: 14, color: 'var(--muted)', flexShrink: 0 }} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="8" cy="4" r="1"/><circle cx="8" cy="8" r="1"/><circle cx="8" cy="12" r="1"/>
              </svg>
            </div>
          </aside>

          {/* Chat area */}
          <div className="chat">
            {/* Chat header */}
            <div className="chat-head">
              <div>
                <div className="title">Q3 pricing guardrails</div>
                <div className="sub">Claude Sonnet 4.6 · Product docs + Sales playbook</div>
              </div>
              <button className="head-btn" title="Share">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 5.5a2 2 0 1 0-1.9-1.4L6.8 6.3A2 2 0 1 0 6.8 9.7l3.3 2.2A2 2 0 1 0 11 10.5l-3.3-2.2"/>
                </svg>
              </button>
              <button className="head-btn" title="More">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="3" cy="8" r="1"/><circle cx="8" cy="8" r="1"/><circle cx="13" cy="8" r="1"/>
                </svg>
              </button>
            </div>

            {/* Thread */}
            <div ref={threadRef} className="thread" />

            {/* Composer */}
            <div className="composer">
              <div className="composer-mid">
                <textarea
                  ref={inputRef}
                  placeholder="Ask anything, attach a KB with @, switch models with ⌘K…"
                  rows={1}
                  readOnly
                />
              </div>
              <div className="composer-bottom">
                <button className="cbtn" title="Attach file">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M11 4L5.5 9.5a2 2 0 0 0 2.8 2.8l5.5-5.5a3.5 3.5 0 0 0-5-5L3.3 7.3a5 5 0 0 0 7 7L15 9.7"/>
                  </svg>
                </button>
                <button className="cbtn ghost" title="Capabilities">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/>
                  </svg>
                </button>
                <span className="cap on reflect" title="Extended thinking">
                  <svg className="ic" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <circle cx="6" cy="6" r="3"/><circle cx="6" cy="6" r="5.2"/>
                  </svg>
                  Reflection
                </span>
                <span className="cap on research" title="Live web">
                  <svg className="ic" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <circle cx="6" cy="6" r="4.5"/><line x1="1.5" y1="6" x2="10.5" y2="6"/>
                    <path d="M6 1.5C7.5 3 8 4.5 8 6s-.5 3-2 4.5C4.5 9 4 7.5 4 6s.5-3 2-4.5z"/>
                  </svg>
                  Research
                </span>
                <span className="cap cap-kb" title="Knowledge bases">
                  <svg className="ic" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M2.5 2.5h5A1.5 1.5 0 0 1 9 4v6l-2.5-1.5L4 10V4a1.5 1.5 0 0 1 1.5-1.5z" transform="translate(1 0)"/>
                  </svg>
                  2 KBs
                  <span className="dot-on"/>
                </span>
                <div style={{ flex: 1 }}/>
                <button ref={sendRef} className="send" aria-label="Send">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="8" y1="13" x2="8" y2="3"/>
                    <polyline points="4,7 8,3 12,7"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
