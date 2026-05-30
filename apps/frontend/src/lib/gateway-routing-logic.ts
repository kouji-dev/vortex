// Pure helpers for the Gateway Routing editor.
//
// The routing policy `rules_json` shape is strategy-specific. We expose
// typed shapes for the common ones the UI edits and a couple of pure
// helpers (validation, priority reorder) that drive the drag-to-reorder
// interaction without touching React.

import type { RoutingPolicy, RoutingStrategy } from './gateway-types'

export const STRATEGY_OPTIONS: { value: RoutingStrategy; label: string; blurb: string }[] = [
  { value: 'static', label: 'Static', blurb: 'Always route to a single concrete model' },
  { value: 'priority', label: 'Priority list', blurb: 'Try candidates top-down; failover on error' },
  { value: 'weighted', label: 'Weighted', blurb: 'Random pick proportional to weights' },
  { value: 'cost_optimized', label: 'Cost-optimized', blurb: 'Cheapest model meeting capability filter' },
  { value: 'latency_optimized', label: 'Latency-optimized', blurb: 'Lowest observed p95 latency' },
  { value: 'capability_match', label: 'Capability match', blurb: 'First candidate meeting required capabilities' },
  { value: 'custom_rules', label: 'Custom rules', blurb: 'Per-request JSON rule expressions' },
]

/** Static strategy: just one target model. */
export interface StaticRules {
  target: string // canonical "provider:model_id"
}

/** Priority strategy: ordered list of targets. */
export interface PriorityRules {
  candidates: string[] // canonical ids, top → bottom is highest → lowest priority
}

/** Weighted strategy: candidates with weights. */
export interface WeightedRules {
  candidates: { target: string; weight: number }[]
}

export function validatePolicyName(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return 'Name required'
  if (trimmed.length > 128) return 'Name too long (max 128)'
  if (!/^[a-zA-Z0-9_-]+$/.test(trimmed)) return 'Name may only use letters, digits, _ and -'
  return null
}

export function validateAliasName(alias: string): string | null {
  const trimmed = alias.trim()
  if (!trimmed) return 'Alias required'
  if (trimmed.length > 128) return 'Alias too long (max 128)'
  if (!/^[a-zA-Z0-9_-]+$/.test(trimmed)) return 'Alias may only use letters, digits, _ and -'
  return null
}

/** Move an item in an ordered array from one index to another. Pure. */
export function reorder<T>(arr: readonly T[], from: number, to: number): T[] {
  if (from === to) return [...arr]
  const out = [...arr]
  if (from < 0 || from >= out.length) return out
  if (to < 0 || to >= out.length) return out
  const [picked] = out.splice(from, 1)
  out.splice(to, 0, picked)
  return out
}

/** Best-effort parse of a policy's `rules_json` into a typed shape. Returns
 * fresh defaults if missing/invalid so the UI never crashes on a half-baked
 * row. The dialog "Save" call re-serialises whatever is in the form. */
export function parseRules(policy: Pick<RoutingPolicy, 'strategy' | 'rules_json'>):
  | { kind: 'static'; rules: StaticRules }
  | { kind: 'priority'; rules: PriorityRules }
  | { kind: 'weighted'; rules: WeightedRules }
  | { kind: 'raw'; rules: unknown } {
  const raw = (policy.rules_json ?? {}) as Record<string, unknown>
  if (policy.strategy === 'static') {
    const target = typeof raw.target === 'string' ? raw.target : ''
    return { kind: 'static', rules: { target } }
  }
  if (policy.strategy === 'priority') {
    const cs = Array.isArray(raw.candidates) ? raw.candidates : []
    const candidates = cs.filter((x): x is string => typeof x === 'string')
    return { kind: 'priority', rules: { candidates } }
  }
  if (policy.strategy === 'weighted') {
    const cs = Array.isArray(raw.candidates) ? raw.candidates : []
    const candidates: WeightedRules['candidates'] = []
    for (const item of cs) {
      if (item && typeof item === 'object') {
        const o = item as Record<string, unknown>
        const target = typeof o.target === 'string' ? o.target : ''
        const weight = typeof o.weight === 'number' ? o.weight : 1
        if (target) candidates.push({ target, weight })
      }
    }
    return { kind: 'weighted', rules: { candidates } }
  }
  return { kind: 'raw', rules: raw }
}
