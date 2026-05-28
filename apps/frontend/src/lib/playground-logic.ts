// apps/frontend/src/lib/playground-logic.ts
// Pure helpers for the Playground page (J8) — text diff + comparison.
import type { PlaygroundRunResult } from './gateway-types'

export type DiffOp = 'same' | 'add' | 'remove'

export interface DiffToken {
  op: DiffOp
  text: string
}

/**
 * Word-level diff using Myers-style LCS. Small, dependency-free.
 * Returns ordered tokens with whitespace preserved between words.
 */
export function wordDiff(a: string, b: string): DiffToken[] {
  const aTok = tokenize(a)
  const bTok = tokenize(b)
  const lcs = lcsTable(aTok, bTok)
  const out: DiffToken[] = []
  let i = aTok.length
  let j = bTok.length
  const stack: DiffToken[] = []
  while (i > 0 && j > 0) {
    if (aTok[i - 1] === bTok[j - 1]) {
      stack.push({ op: 'same', text: aTok[i - 1] })
      i--
      j--
    } else if (lcs[i - 1][j] >= lcs[i][j - 1]) {
      stack.push({ op: 'remove', text: aTok[i - 1] })
      i--
    } else {
      stack.push({ op: 'add', text: bTok[j - 1] })
      j--
    }
  }
  while (i > 0) { stack.push({ op: 'remove', text: aTok[--i] }) }
  while (j > 0) { stack.push({ op: 'add', text: bTok[--j] }) }
  for (let k = stack.length - 1; k >= 0; k--) out.push(stack[k])
  return mergeAdjacent(out)
}

function tokenize(s: string): string[] {
  // Keep whitespace as standalone tokens so diff renders nicely.
  return s.split(/(\s+)/).filter((t) => t.length > 0)
}

function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length
  const n = b.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1
      else dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }
  return dp
}

function mergeAdjacent(toks: DiffToken[]): DiffToken[] {
  const out: DiffToken[] = []
  for (const t of toks) {
    const last = out[out.length - 1]
    if (last && last.op === t.op) last.text += t.text
    else out.push({ ...t })
  }
  return out
}

/** Summary line for compare cards. */
export function summarize(r: PlaygroundRunResult): string {
  return `${r.tokens_in}/${r.tokens_out} tok · ${r.latency_ms}ms · $${(r.cost_cents / 100).toFixed(4)}`
}

/** Clamp 2..4 model picks. */
export function clampModelPicks(picks: string[]): string[] {
  const unique = Array.from(new Set(picks)).filter(Boolean)
  return unique.slice(0, 4)
}
