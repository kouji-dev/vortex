// apps/frontend/src/lib/guardrails-logic.ts
// Pure helpers for guardrail policy editing + live test pane.
import type {
  GuardrailAction,
  GuardrailBundle,
  GuardrailStep,
  GuardrailVerdict,
} from './gateway-types'

const ACTION_PRIORITY: Record<GuardrailAction, number> = {
  block: 3,
  redact: 2,
  flag: 1,
  allow: 0,
}

/** Resolve the strongest action across a list of verdicts. */
export function resolveFinalDecision(verdicts: GuardrailVerdict[]): GuardrailAction {
  let best: GuardrailAction = 'allow'
  for (const v of verdicts) {
    if (ACTION_PRIORITY[v.decision] > ACTION_PRIORITY[best]) best = v.decision
  }
  return best
}

/** Reorder a step within input/output phase (UI uses drag handles). */
export function reorderStep(
  bundle: GuardrailBundle,
  phase: 'input' | 'output',
  from: number,
  to: number,
): GuardrailBundle {
  const list = bundle[phase].slice()
  if (from < 0 || from >= list.length || to < 0 || to >= list.length) return bundle
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
  return { ...bundle, [phase]: list }
}

export function addStep(
  bundle: GuardrailBundle,
  phase: 'input' | 'output',
  step: GuardrailStep,
): GuardrailBundle {
  return { ...bundle, [phase]: [...bundle[phase], step] }
}

export function removeStep(
  bundle: GuardrailBundle,
  phase: 'input' | 'output',
  index: number,
): GuardrailBundle {
  const list = bundle[phase].filter((_, i) => i !== index)
  return { ...bundle, [phase]: list }
}

/** Decision badge style class fragment. */
export function decisionBadge(d: GuardrailAction): string {
  switch (d) {
    case 'block':
      return 'pill pill-red'
    case 'redact':
      return 'pill pill-yellow'
    case 'flag':
      return 'pill pill-blue'
    case 'allow':
      return 'pill pill-green'
  }
}
