// apps/frontend/src/lib/evals-logic.ts
// Pure helpers for the Evals page (J9).
import type { EvalRecord, EvalRunRowResult, EvalRunSummary, EvalTestSet } from './gateway-types'

/** Compute a summary from raw row results. */
export function summarizeRun(target_model: string, rows: EvalRunRowResult[]): EvalRunSummary {
  const passed = rows.filter((r) => r.passed).length
  const failed = rows.length - passed
  const total_cost_cents = rows.reduce((s, r) => s + r.cost_cents, 0)
  const latencies = rows.map((r) => r.latency_ms).sort((a, b) => a - b)
  const p95_latency_ms = latencies.length
    ? latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * 0.95))]
    : 0
  const pass_rate = rows.length ? passed / rows.length : 0
  return { target_model, pass_rate, p95_latency_ms, total_cost_cents, passed, failed }
}

/** Detect regression vs baseline run (5pp drop in pass-rate = regression). */
export function detectRegression(
  baseline: EvalRunSummary,
  current: EvalRunSummary,
  thresholdPp = 5,
): boolean {
  return baseline.pass_rate - current.pass_rate >= thresholdPp / 100
}

/** Validate that records are well-formed before saving a test set. */
export function validateTestSet(s: Pick<EvalTestSet, 'name' | 'records'>): string | null {
  if (!s.name?.trim()) return 'Name is required'
  if (!Array.isArray(s.records) || s.records.length === 0) return 'At least one record is required'
  for (let i = 0; i < s.records.length; i++) {
    const r = s.records[i]
    if (!r.input?.trim()) return `Record ${i + 1}: input is required`
    if (r.judge !== 'exact' && r.judge !== 'regex' && r.judge !== 'llm' && r.judge !== 'custom') {
      return `Record ${i + 1}: unknown judge`
    }
  }
  return null
}

/** Format pass-rate as "85.0%". */
export function fmtPassRate(rate: number): string {
  return (rate * 100).toFixed(1) + '%'
}

/** Build a blank record. */
export function blankRecord(id: string): EvalRecord {
  return { id, input: '', expected: '', judge: 'exact' }
}
