import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  aggregateCostCents,
  buildTerminalLog,
  canCancel,
  canPause,
  canResume,
  eventLabel,
  fileTreeFromEvents,
  formatCents,
  isRunTerminal,
  isTerminal,
  parseSseDataLine,
  runStatusBadgeClass,
  statusBadgeClass,
  tasksStats,
  workerStateBadgeClass,
} from './workers-logic.ts'
import type { WorkerEvent } from './workers-types.ts'

test('workerStateBadgeClass: idle ok, error bad, stopped warn', () => {
  assert.equal(workerStateBadgeClass('idle'), 'gw-badge ok')
  assert.equal(workerStateBadgeClass('error'), 'gw-badge bad')
  assert.equal(workerStateBadgeClass('stopped'), 'gw-badge warn')
  assert.equal(workerStateBadgeClass('running'), 'gw-badge')
  assert.equal(workerStateBadgeClass('provisioning'), 'gw-badge')
})

test('runStatusBadgeClass: success ok, error bad, running default', () => {
  assert.equal(runStatusBadgeClass('success'), 'gw-badge ok')
  assert.equal(runStatusBadgeClass('error'), 'gw-badge bad')
  assert.equal(runStatusBadgeClass('running'), 'gw-badge')
  assert.equal(runStatusBadgeClass('finished'), 'gw-badge')
})

test('isRunTerminal: success/finished/error terminal, running not', () => {
  assert.equal(isRunTerminal('success'), true)
  assert.equal(isRunTerminal('finished'), true)
  assert.equal(isRunTerminal('error'), true)
  assert.equal(isRunTerminal('running'), false)
})

test('statusBadgeClass: ok for completed', () => {
  assert.equal(statusBadgeClass('completed'), 'gw-badge ok')
})

test('statusBadgeClass: bad for failed/cancelled', () => {
  assert.equal(statusBadgeClass('failed'), 'gw-badge bad')
  assert.equal(statusBadgeClass('cancelled'), 'gw-badge bad')
})

test('statusBadgeClass: warn for awaiting/paused', () => {
  assert.equal(statusBadgeClass('awaiting_pr_approval'), 'gw-badge warn')
  assert.equal(statusBadgeClass('awaiting_plan_approval'), 'gw-badge warn')
  assert.equal(statusBadgeClass('paused'), 'gw-badge warn')
})

test('statusBadgeClass: neutral for queued/executing/planning', () => {
  assert.equal(statusBadgeClass('queued'), 'gw-badge')
  assert.equal(statusBadgeClass('executing'), 'gw-badge')
  assert.equal(statusBadgeClass('planning'), 'gw-badge')
})

test('isTerminal', () => {
  assert.equal(isTerminal('completed'), true)
  assert.equal(isTerminal('failed'), true)
  assert.equal(isTerminal('cancelled'), true)
  assert.equal(isTerminal('executing'), false)
})

test('canPause: only when executing', () => {
  assert.equal(canPause('executing'), true)
  assert.equal(canPause('paused'), false)
  assert.equal(canPause('queued'), false)
})

test('canResume: only when paused', () => {
  assert.equal(canResume('paused'), true)
  assert.equal(canResume('executing'), false)
})

test('canCancel: any non-terminal', () => {
  assert.equal(canCancel('queued'), true)
  assert.equal(canCancel('executing'), true)
  assert.equal(canCancel('paused'), true)
  assert.equal(canCancel('completed'), false)
  assert.equal(canCancel('failed'), false)
  assert.equal(canCancel('cancelled'), false)
})

test('formatCents: null and zero', () => {
  assert.equal(formatCents(null), '$0.00')
  assert.equal(formatCents(undefined), '$0.00')
  assert.equal(formatCents(0), '$0.00')
})

test('formatCents: integer cents', () => {
  assert.equal(formatCents(150), '$1.50')
  assert.equal(formatCents(12345), '$123.45')
})

test('eventLabel: known kinds', () => {
  assert.equal(eventLabel('agent_thought'), 'Thought')
  assert.equal(eventLabel('tool_call'), 'Tool')
  assert.equal(eventLabel('shell_output'), 'Shell')
})

test('eventLabel: unknown falls back to raw', () => {
  assert.equal(eventLabel('something_new'), 'something_new')
})

function makeEvent(kind: string, payload: Record<string, unknown>, n = 1): WorkerEvent {
  return { id: `e-${n}`, kind, ts: '2026-05-28T12:00:00Z', payload }
}

test('buildTerminalLog: concatenates shell_output chunks in order', () => {
  const events: WorkerEvent[] = [
    makeEvent('agent_thought', { text: 'plan' }),
    makeEvent('shell_output', { chunk: 'hello\n' }, 2),
    makeEvent('tool_call', { tool: 'shell' }, 3),
    makeEvent('shell_output', { chunk: 'world\n' }, 4),
  ]
  assert.equal(buildTerminalLog(events), 'hello\nworld\n')
})

test('buildTerminalLog: ignores non-string chunks', () => {
  const events: WorkerEvent[] = [
    makeEvent('shell_output', { chunk: 'a' }),
    makeEvent('shell_output', { chunk: 42 }),
    makeEvent('shell_output', { chunk: 'b' }),
  ]
  assert.equal(buildTerminalLog(events), 'ab')
})

test('fileTreeFromEvents: dedupes by path with last-write-wins', () => {
  const events: WorkerEvent[] = [
    makeEvent('file_changed', { path: 'a.py', action: 'create' }),
    makeEvent('file_changed', { path: 'b.py', action: 'edit' }),
    makeEvent('file_changed', { path: 'a.py', action: 'edit' }),
  ]
  const out = fileTreeFromEvents(events)
  assert.deepEqual(out, [
    { path: 'a.py', action: 'edit' },
    { path: 'b.py', action: 'edit' },
  ])
})

test('aggregateCostCents: last value wins', () => {
  const events: WorkerEvent[] = [
    makeEvent('cost_update', { cents: 10 }),
    makeEvent('cost_update', { cents: 25 }),
    makeEvent('cost_update', { cents: 42 }),
  ]
  assert.equal(aggregateCostCents(events), 42)
})

test('aggregateCostCents: zero when none', () => {
  assert.equal(aggregateCostCents([]), 0)
})

test('parseSseDataLine: valid', () => {
  const line = `data: {"id":"e-1","kind":"agent_thought","ts":"2026-05-28T12:00:00Z","payload":{"text":"hi"}}`
  const got = parseSseDataLine(line)
  assert.deepEqual(got, {
    id: 'e-1',
    kind: 'agent_thought',
    ts: '2026-05-28T12:00:00Z',
    payload: { text: 'hi' },
  })
})

test('parseSseDataLine: ignores non-data lines', () => {
  assert.equal(parseSseDataLine(': keepalive'), null)
  assert.equal(parseSseDataLine('event: agent_thought'), null)
})

test('parseSseDataLine: invalid json returns null', () => {
  assert.equal(parseSseDataLine('data: not-json'), null)
})

test('parseSseDataLine: missing required fields returns null', () => {
  assert.equal(parseSseDataLine('data: {"kind":"x"}'), null)
})

test('parseSseDataLine: missing payload defaults to {}', () => {
  const got = parseSseDataLine('data: {"id":"a","kind":"x","ts":"t"}')
  assert.deepEqual(got?.payload, {})
})

test('tasksStats: counts by bucket', () => {
  const stats = tasksStats([
    { status: 'completed', completed_at: 't' },
    { status: 'completed', completed_at: 't' },
    { status: 'failed', completed_at: 't' },
    { status: 'executing', completed_at: null },
    { status: 'cancelled', completed_at: 't' },
  ])
  assert.equal(stats.total, 5)
  assert.equal(stats.completed, 2)
  assert.equal(stats.failed, 1)
  assert.equal(stats.cancelled, 1)
  assert.equal(stats.active, 1)
  assert.equal(stats.successRate, 0.4)
})

test('tasksStats: empty', () => {
  const stats = tasksStats([])
  assert.equal(stats.total, 0)
  assert.equal(stats.successRate, 0)
})
