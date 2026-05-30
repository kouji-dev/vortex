// Pure logic for the workers UI — formatters, badges, grouping, SSE parsing.
// Unit-tested with node:test; no React or DOM imports.

import type {
  EventKind,
  InstanceRunStatus,
  TaskStatus,
  WorkerEvent,
  WorkerState,
} from './workers-types'

/** Map a TaskStatus to a CSS badge class (matches gateway badge palette). */
export function statusBadgeClass(s: TaskStatus): string {
  switch (s) {
    case 'completed':
      return 'gw-badge ok'
    case 'executing':
    case 'planning':
      return 'gw-badge'
    case 'awaiting_plan_approval':
    case 'awaiting_pr_approval':
      return 'gw-badge warn'
    case 'paused':
      return 'gw-badge warn'
    case 'queued':
      return 'gw-badge'
    case 'failed':
    case 'cancelled':
      return 'gw-badge bad'
    default:
      return 'gw-badge'
  }
}

/** True if a task is in a terminal state. */
export function isTerminal(s: TaskStatus): boolean {
  return s === 'completed' || s === 'failed' || s === 'cancelled'
}

/** True if a task can be paused right now. */
export function canPause(s: TaskStatus): boolean {
  return s === 'executing'
}

/** True if a task can be resumed. */
export function canResume(s: TaskStatus): boolean {
  return s === 'paused'
}

/** True if a task can be cancelled. */
export function canCancel(s: TaskStatus): boolean {
  return !isTerminal(s)
}

/** Format ``$x.yy`` from cents. */
export function formatCents(cents: number | null | undefined): string {
  if (cents == null) return '$0.00'
  return `$${(cents / 100).toFixed(2)}`
}

/** Format an ISO-8601 timestamp as ``HH:MM:SS``. */
export function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

/** Visual ordering of event kinds in the live stream UI. */
export const EVENT_KIND_LABEL: Record<EventKind, string> = {
  agent_thought: 'Thought',
  tool_call: 'Tool',
  tool_result: 'Result',
  file_changed: 'File',
  shell_output: 'Shell',
  pr_created: 'PR',
  error: 'Error',
  phase_changed: 'Phase',
  approval_requested: 'Approval',
  user_message: 'You',
  cost_update: 'Cost',
  egress_blocked: 'Egress',
  secret_blocked: 'Secret',
}

/** Best-effort label for an event of any kind. */
export function eventLabel(kind: string): string {
  return (EVENT_KIND_LABEL as Record<string, string>)[kind] ?? kind
}

/** Filter shell_output events into a single concatenated terminal log. */
export function buildTerminalLog(events: WorkerEvent[]): string {
  const parts: string[] = []
  for (const e of events) {
    if (e.kind !== 'shell_output') continue
    const chunk = e.payload?.chunk
    if (typeof chunk === 'string') parts.push(chunk)
  }
  return parts.join('')
}

/** Group ``file_changed`` events by path; later events win. */
export function fileTreeFromEvents(events: WorkerEvent[]): { path: string; action: string }[] {
  const seen = new Map<string, string>()
  for (const e of events) {
    if (e.kind !== 'file_changed') continue
    const path = String(e.payload?.path ?? '')
    const action = String(e.payload?.action ?? 'edit')
    if (!path) continue
    seen.set(path, action)
  }
  return [...seen.entries()].map(([path, action]) => ({ path, action }))
}

/** Aggregate cost from cost_update events; last value wins. */
export function aggregateCostCents(events: WorkerEvent[]): number {
  let total = 0
  for (const e of events) {
    if (e.kind !== 'cost_update') continue
    const v = e.payload?.cents
    if (typeof v === 'number') total = v
  }
  return total
}

/** Parse a single SSE payload field — `data: {json}\n\n`. */
export function parseSseDataLine(line: string): WorkerEvent | null {
  if (!line.startsWith('data:')) return null
  const rest = line.slice('data:'.length).trim()
  if (!rest) return null
  try {
    const obj = JSON.parse(rest) as Partial<WorkerEvent>
    if (!obj.id || !obj.kind || !obj.ts) return null
    return {
      id: String(obj.id),
      kind: String(obj.kind),
      ts: String(obj.ts),
      payload: (obj.payload as Record<string, unknown>) ?? {},
    }
  } catch {
    return null
  }
}

/** Sum success/fail counts over a list of tasks. */
export function tasksStats(tasks: { status: TaskStatus; completed_at: string | null }[]) {
  let completed = 0
  let failed = 0
  let cancelled = 0
  let active = 0
  for (const t of tasks) {
    if (t.status === 'completed') completed++
    else if (t.status === 'failed') failed++
    else if (t.status === 'cancelled') cancelled++
    else active++
  }
  const total = tasks.length
  const successRate = total > 0 ? completed / total : 0
  return { total, completed, failed, cancelled, active, successRate }
}

// ── worker instances (worker-centric) ────────────────────────────

/** Map a worker lifecycle state to a CSS badge class. */
export function workerStateBadgeClass(s: WorkerState): string {
  switch (s) {
    case 'idle':
      return 'gw-badge ok'
    case 'running':
    case 'provisioning':
      return 'gw-badge'
    case 'error':
      return 'gw-badge bad'
    case 'stopped':
      return 'gw-badge warn'
    default:
      return 'gw-badge'
  }
}

/** Map an instance-run status to a CSS badge class. */
export function runStatusBadgeClass(s: InstanceRunStatus): string {
  switch (s) {
    case 'success':
      return 'gw-badge ok'
    case 'running':
      return 'gw-badge'
    case 'finished':
      return 'gw-badge'
    case 'error':
      return 'gw-badge bad'
    default:
      return 'gw-badge'
  }
}

/** True if an instance run is in a terminal state. */
export function isRunTerminal(s: InstanceRunStatus): boolean {
  return s === 'success' || s === 'finished' || s === 'error'
}
