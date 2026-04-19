// landing/src/lib/demo-chips.ts

const PREVIEW = "Based on your Q3 report, three critical risks stand out for Q4: customer concentration (42% ARR in top 3 accounts), margin compression ($42M R&D up 34% YoY), and infrastructure overage ($2.1M over budget). Here's the Q4 action plan…"

const PRISM_SVG = `<svg viewBox="0 0 80 80" fill="none" width="10" height="10" style="animation:prismSpin 1s linear infinite"><polygon points="40,8 68,40 40,72 12,40" fill="none" stroke="currentColor" stroke-width="5"/></svg>`
const CHECK_SVG = `<svg style="color:#22c55e;width:10px;height:10px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
const BRAIN_SVG = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2a9 9 0 0 1 0 18 4.5 4.5 0 0 1 0-9"/><path d="M11.5 11.5h8"/></svg>`
const LIB_SVG   = `<svg style="width:12px;height:12px;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`
const CHEV_SVG  = `<svg style="width:10px;height:10px;opacity:.4;flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`

export interface ChipDemoRefs {
  row:      HTMLElement
  thinkRow: HTMLElement
  respEl:   HTMLElement
  txtEl:    HTMLElement
  labelEl:  HTMLElement
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => { signal?.removeEventListener('abort', onAbort); res() }, ms)
    function onAbort() { clearTimeout(t); rej(new DOMException('Aborted', 'AbortError')) }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

export async function runChipDemo(refs: ChipDemoRefs, signal: AbortSignal): Promise<void> {
  const { row, thinkRow, respEl, txtEl, labelEl } = refs

  try {
    // Reset
    row.innerHTML        = ''
    thinkRow.style.display = 'none'
    respEl.style.display   = 'none'
    txtEl.textContent      = ''
    labelEl.textContent    = 'vortex · processing…'

    await sleep(600, signal)

    // Memory chip
    const mem = document.createElement('div')
    mem.className = 'chip chip-memory'
    mem.style.cssText = 'opacity:0;transform:translateY(6px);transition:opacity .3s,transform .3s'
    mem.innerHTML = `${BRAIN_SVG}<span>Loading memories…</span>${PRISM_SVG}`
    row.appendChild(mem)
    await sleep(40, signal)
    mem.style.opacity = '1'
    mem.style.transform = 'none'
    await sleep(1000, signal)
    mem.innerHTML = `${BRAIN_SVG}<span>3 memories loaded</span>${CHECK_SVG}`
    await sleep(220, signal)

    // KB chip
    const kb = document.createElement('div')
    kb.className = 'chip chip-kb'
    kb.style.cssText = 'opacity:0;transform:translateY(6px);transition:opacity .3s,transform .3s'
    kb.innerHTML = `${LIB_SVG}<span>Searching knowledge base…</span>${PRISM_SVG}`
    row.appendChild(kb)
    await sleep(40, signal)
    kb.style.opacity = '1'
    kb.style.transform = 'none'
    await sleep(1100, signal)
    kb.innerHTML = `${LIB_SVG}<span>KB Searched "Q3 risks Q4 planning"</span>${CHECK_SVG}${CHEV_SVG}`
    labelEl.textContent = 'vortex · thinking…'
    await sleep(300, signal)

    // Thinking dots
    thinkRow.style.display = 'flex'
    await sleep(900, signal)
    thinkRow.style.display = 'none'

    // Stream response
    labelEl.textContent      = 'vortex · streaming…'
    respEl.style.display     = 'flex'
    respEl.style.opacity     = '0'
    respEl.style.transition  = 'opacity .4s'
    await sleep(30, signal)
    respEl.style.opacity = '1'

    let built = ''
    for (const ch of PREVIEW) {
      if (signal.aborted) return
      built += ch
      txtEl.innerHTML = built + '<span class="cursor"></span>'
      await sleep(ch === ' ' ? 16 : ch === ',' || ch === '.' ? 45 : 18, signal)
    }
    txtEl.innerHTML     = built
    labelEl.textContent = 'vortex · done'

  } catch (e) {
    if ((e as DOMException).name !== 'AbortError') throw e
  }
}
