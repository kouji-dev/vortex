const USER_MSG = "What were the key risks from our Q3 report, and how should we address them in Q4 planning?"

const AI_RESPONSE = `Based on your Q3 report and Q4 planning brief, three critical risks stand out:

**1. Customer concentration** — top 3 customers represent 42% of ARR, with renewals clustering in Q1. Q4 is your window to lock in expansions before renewal pressure hits.

**2. Margin compression** — $42M R&D spend is up 34% YoY. The board needs a clear ROI story by December 15. Prepare the narrative now.

**3. Infrastructure overage** — cloud costs are tracking $2.1M above budget. Migrating to reserved instances can recover ~$800K before year-end.`

// SVG strings — kept as template literals to avoid React dependency in this module
const PRISM_SVG   = `<svg viewBox="0 0 80 80" fill="none" width="10" height="10" style="animation:prismSpin 1s linear infinite"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="currentColor" stroke-width="5"/></svg>`
const CHECK_SVG   = `<svg style="color:#22c55e;width:10px;height:10px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
const BRAIN_SVG   = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/><path d="M11.5 11.5h8"/></svg>`
const LIB_SVG     = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`
const CHEV_SVG    = `<svg style="width:10px;height:10px;opacity:.4;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`
const AI_AVATAR   = `<svg viewBox="0 0 80 80" fill="none" width="14" height="14"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="white" stroke-width="5"/></svg>`

export interface HeroDemoRefs {
  thread:    HTMLElement
  composer:  HTMLTextAreaElement
  charCount: HTMLElement
  sendBtn:   HTMLElement
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}

function addEl(thread: HTMLElement, html: string): HTMLElement {
  const div = document.createElement('div')
  div.innerHTML = html
  const el = div.firstElementChild as HTMLElement
  el.style.cssText = 'opacity:0;transform:translateY(8px);transition:opacity .4s ease,transform .4s ease'
  thread.appendChild(el)
  requestAnimationFrame(() => requestAnimationFrame(() => {
    el.style.opacity = '1'
    el.style.transform = 'none'
  }))
  thread.scrollTop = thread.scrollHeight
  return el
}

async function typeInComposer(composer: HTMLTextAreaElement, charCount: HTMLElement, text: string, stopped: { value: boolean }): Promise<void> {
  composer.value = ''
  for (let i = 0; i <= text.length; i++) {
    if (stopped.value) return
    composer.value = text.slice(0, i)
    charCount.textContent = `${i} / 2000`
    await sleep(26 + Math.random() * 18)
  }
}

async function streamText(el: HTMLElement, thread: HTMLElement, text: string, stopped: { value: boolean }): Promise<void> {
  let built = ''
  for (const ch of text) {
    if (stopped.value) return
    built += ch
    el.innerHTML = built.replace(/\*\*(.*?)\*\*/g, '<strong style="color:#e8e4ff">$1</strong>') + '<span class="cursor"></span>'
    thread.scrollTop = thread.scrollHeight
    await sleep(ch === ' ' ? 16 : ch === '\n' ? 55 : 20)
  }
  el.innerHTML = built.replace(/\*\*(.*?)\*\*/g, '<strong style="color:#e8e4ff">$1</strong>')
}

async function runOnce(refs: HeroDemoRefs, stopped: { value: boolean }): Promise<void> {
  const { thread, composer, charCount, sendBtn } = refs
  if (stopped.value) return

  await sleep(1000)
  if (stopped.value) return

  await typeInComposer(composer, charCount, USER_MSG, stopped)
  await sleep(450)
  if (stopped.value) return

  sendBtn.style.transform = 'scale(0.9)'
  await sleep(100)
  if (stopped.value) return
  sendBtn.style.transform = ''
  composer.value = ''
  charCount.textContent = '0 / 2000'

  addEl(thread, `<div class="msg-user"><div class="msg-user-bubble">${USER_MSG}</div></div>`)
  await sleep(280)
  if (stopped.value) return

  // Chips row
  const chipsRow = addEl(thread, `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:4px"></div>`)
  const memChip = document.createElement('div')
  memChip.className = 'chip chip-memory'
  memChip.innerHTML = `${BRAIN_SVG}<span>Loading memories…</span>${PRISM_SVG}`
  chipsRow.appendChild(memChip)
  await sleep(950)
  if (stopped.value) return

  memChip.innerHTML = `${BRAIN_SVG}<span>3 memories loaded</span>${CHECK_SVG}`
  await sleep(180)

  const kbChip = document.createElement('div')
  kbChip.className = 'chip chip-kb'
  kbChip.style.cssText = 'opacity:0;transform:translateY(6px);transition:opacity .3s,transform .3s'
  kbChip.innerHTML = `${LIB_SVG}<span>Searching KB…</span>${PRISM_SVG}`
  chipsRow.appendChild(kbChip)
  requestAnimationFrame(() => requestAnimationFrame(() => {
    kbChip.style.opacity = '1'
    kbChip.style.transform = 'none'
  }))
  await sleep(1050)
  if (stopped.value) return

  kbChip.innerHTML = `${LIB_SVG}<span>KB Searched "Q3 risks Q4 planning"</span>${CHECK_SVG}${CHEV_SVG}`
  await sleep(280)

  // Thinking dots
  const thinkEl = addEl(thread, `<div style="display:flex;align-items:center;gap:5px;padding:8px 12px"><div class="thinking-dot"></div><div class="thinking-dot" style="animation-delay:.18s"></div><div class="thinking-dot" style="animation-delay:.36s"></div></div>`)
  await sleep(820)
  if (stopped.value) return
  thread.removeChild(thinkEl)

  // AI response
  const aiMsg = addEl(thread, `<div class="msg-ai"><div class="msg-ai-avatar">${AI_AVATAR}</div><div class="msg-ai-body"><div class="msg-ai-name">Vortex · claude-sonnet-4-6</div><div class="msg-ai-text"></div></div></div>`)
  const aiText = aiMsg.querySelector('.msg-ai-text') as HTMLElement
  if (stopped.value) return
  await streamText(aiText, thread, AI_RESPONSE, stopped)

  await sleep(380)
  if (stopped.value) return
  addEl(thread, `<div style="display:flex;align-items:center;gap:6px;padding:6px 10px;background:rgba(59,7,100,.15);border:1px solid rgba(126,34,206,.15);border-radius:8px;font-size:11px;color:#a78bfa;margin-top:4px">${LIB_SVG}<span>Used: Finance Docs (3 chunks), Q4 Planning Brief (1 chunk)</span></div>`)

  await sleep(6000)
  if (stopped.value) return
  thread.innerHTML = ''
  runOnce(refs, stopped)
}

export function startHeroDemo(refs: HeroDemoRefs): () => void {
  const stopped = { value: false }
  runOnce(refs, stopped)
  return () => { stopped.value = true }
}
