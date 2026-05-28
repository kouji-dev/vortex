// apps/frontend/src/lib/guardrails-logic.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  addStep,
  decisionBadge,
  removeStep,
  reorderStep,
  resolveFinalDecision,
} from './guardrails-logic'
import type { GuardrailBundle } from './gateway-types'

test('resolveFinalDecision picks strongest action', () => {
  assert.equal(
    resolveFinalDecision([
      { guardrail: 'a', decision: 'allow', matches: [], redacted_text: null, reason: '' },
      { guardrail: 'b', decision: 'flag', matches: [], redacted_text: null, reason: '' },
      { guardrail: 'c', decision: 'redact', matches: [], redacted_text: null, reason: '' },
    ]),
    'redact',
  )
  assert.equal(
    resolveFinalDecision([
      { guardrail: 'a', decision: 'redact', matches: [], redacted_text: null, reason: '' },
      { guardrail: 'b', decision: 'block', matches: [], redacted_text: null, reason: '' },
    ]),
    'block',
  )
  assert.equal(resolveFinalDecision([]), 'allow')
})

test('addStep / removeStep / reorderStep are immutable + correct', () => {
  const empty: GuardrailBundle = { input: [], output: [] }
  const s1 = { kind: 'regex' as const, config: {}, on_match: 'block' as const }
  const s2 = { kind: 'presidio' as const, config: {}, on_match: 'redact' as const }
  const s3 = { kind: 'secret_scanner' as const, config: {}, on_match: 'flag' as const }

  const b1 = addStep(empty, 'input', s1)
  assert.equal(empty.input.length, 0, 'addStep must not mutate input')
  assert.equal(b1.input.length, 1)

  const b2 = addStep(addStep(b1, 'input', s2), 'input', s3)
  assert.deepEqual(
    b2.input.map((s) => s.kind),
    ['regex', 'presidio', 'secret_scanner'],
  )

  const reordered = reorderStep(b2, 'input', 0, 2)
  assert.deepEqual(
    reordered.input.map((s) => s.kind),
    ['presidio', 'secret_scanner', 'regex'],
  )

  // out-of-bounds is a no-op (returns original)
  assert.equal(reorderStep(b2, 'input', 5, 0), b2)

  const removed = removeStep(b2, 'input', 1)
  assert.deepEqual(
    removed.input.map((s) => s.kind),
    ['regex', 'secret_scanner'],
  )
})

test('decisionBadge maps to a pill class', () => {
  assert.match(decisionBadge('block'), /red/)
  assert.match(decisionBadge('redact'), /yellow/)
  assert.match(decisionBadge('flag'), /blue/)
  assert.match(decisionBadge('allow'), /green/)
})
