import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { filterReasoning, filterToolLog } from './workers-panels.ts'
import type { WorkerEvent } from './workers-types.ts'

function ev(
  id: string,
  kind: WorkerEvent['kind'],
  payload: Record<string, unknown>,
  ts = '2026-01-01T00:00:00Z',
): WorkerEvent {
  return { id, run_id: 'r', kind, payload, ts } as WorkerEvent
}

test('filterReasoning: keeps only agent_thought with non-empty text', () => {
  const evs = [
    ev('1', 'agent_thought', { text: 'thinking' }),
    ev('2', 'tool_call', { tool: 'shell' }),
    ev('3', 'agent_thought', { text: '' }),
    ev('4', 'agent_thought', { text: 'next step' }),
  ]
  const out = filterReasoning(evs)
  assert.equal(out.length, 2)
  assert.equal(out[0].text, 'thinking')
  assert.equal(out[1].text, 'next step')
})

test('filterReasoning: trims whitespace and drops blank-only', () => {
  const evs = [
    ev('1', 'agent_thought', { text: '   ' }),
    ev('2', 'agent_thought', { text: '  ok  ' }),
  ]
  const out = filterReasoning(evs)
  assert.equal(out.length, 1)
  assert.equal(out[0].text, 'ok')
})

test('filterToolLog: pairs tool_call with following tool_result for same tool', () => {
  const evs = [
    ev('1', 'tool_call', { tool: 'shell', args: { cmd: ['ls'] } }),
    ev('2', 'shell_output', { chunk: 'a' }),
    ev('3', 'tool_result', { tool: 'shell', ok: true, output: 'done' }),
  ]
  const out = filterToolLog(evs)
  assert.equal(out.length, 1)
  assert.equal(out[0].tool, 'shell')
  assert.equal(out[0].ok, true)
  assert.equal(out[0].output, 'done')
  assert.equal(out[0].error, null)
})

test('filterToolLog: pending call (no result yet) has ok=null', () => {
  const evs = [ev('1', 'tool_call', { tool: 'edit', args: { path: 'a.ts' } })]
  const out = filterToolLog(evs)
  assert.equal(out.length, 1)
  assert.equal(out[0].ok, null)
})

test('filterToolLog: records error on failure', () => {
  const evs = [
    ev('1', 'tool_call', { tool: 'shell' }),
    ev('2', 'tool_result', { tool: 'shell', ok: false, error: 'boom' }),
  ]
  const out = filterToolLog(evs)
  assert.equal(out.length, 1)
  assert.equal(out[0].ok, false)
  assert.equal(out[0].error, 'boom')
})

test('filterToolLog: pairs by call_id when present', () => {
  const evs = [
    ev('1', 'tool_call', { tool: 'shell', call_id: 'a' }),
    ev('2', 'tool_call', { tool: 'shell', call_id: 'b' }),
    ev('3', 'tool_result', { tool: 'shell', call_id: 'b', ok: false, error: 'x' }),
    ev('4', 'tool_result', { tool: 'shell', call_id: 'a', ok: true }),
  ]
  const out = filterToolLog(evs)
  assert.equal(out.length, 2)
  // Index 0 corresponds to first call (call_id=a) → ok true.
  assert.equal(out[0].ok, true)
  // Index 1 corresponds to second call (call_id=b) → ok false.
  assert.equal(out[1].ok, false)
})

test('filterToolLog: orphan tool_result still surfaces', () => {
  const evs = [
    ev('1', 'tool_result', { tool: 'unknown', ok: false, error: 'no call' }),
  ]
  const out = filterToolLog(evs)
  assert.equal(out.length, 1)
  assert.equal(out[0].tool, 'unknown')
  assert.equal(out[0].ok, false)
  assert.equal(out[0].error, 'no call')
})

test('filterToolLog: ignores non-tool events', () => {
  const evs = [
    ev('1', 'agent_thought', { text: 'x' }),
    ev('2', 'shell_output', { chunk: 'y' }),
    ev('3', 'file_changed', { path: 'a.ts' }),
  ]
  assert.equal(filterToolLog(evs).length, 0)
})
