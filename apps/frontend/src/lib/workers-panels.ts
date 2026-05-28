/**
 * Pure-logic filters for the worker live-view side panels.
 *
 * Each side pane is a thin presentation layer over a single filter
 * function below. Keeping the logic pure means each pane is unit-testable
 * without rendering React.
 *
 * Panes:
 *  - Terminal      → shell_output
 *  - File tree     → file_changed (path + action, dedup by path, last wins)
 *  - Reasoning     → agent_thought (text)
 *  - Tool log      → tool_call + tool_result (pairs)
 */
import type { WorkerEvent } from './workers-types'

export type ReasoningEntry = {
  id: string
  ts: string
  text: string
}

export type ToolLogEntry = {
  id: string
  ts: string
  tool: string
  args: unknown
  ok: boolean | null // null = pending (no result yet)
  output: unknown
  error: string | null
}

/** agent_thought entries only — chronological. */
export function filterReasoning(events: WorkerEvent[]): ReasoningEntry[] {
  const out: ReasoningEntry[] = []
  for (const e of events) {
    if (e.kind !== 'agent_thought') continue
    const text = String(e.payload?.text ?? '').trim()
    if (!text) continue
    out.push({ id: e.id, ts: e.ts, text })
  }
  return out
}

/**
 * Pair every tool_call with its tool_result by ``call_id`` if present, else
 * by the next tool_result for the same tool name.
 *
 * Each call appears in the output, with ``ok=null`` when no result yet.
 */
export function filterToolLog(events: WorkerEvent[]): ToolLogEntry[] {
  const entries: ToolLogEntry[] = []
  const pendingByCallId = new Map<string, number>()
  const pendingByTool = new Map<string, number[]>()

  for (const e of events) {
    if (e.kind === 'tool_call') {
      const tool = String(e.payload?.tool ?? '')
      const callId = String(e.payload?.call_id ?? '')
      const entry: ToolLogEntry = {
        id: e.id,
        ts: e.ts,
        tool,
        args: e.payload?.args ?? e.payload?.cmd ?? {},
        ok: null,
        output: null,
        error: null,
      }
      const idx = entries.length
      entries.push(entry)
      if (callId) pendingByCallId.set(callId, idx)
      const list = pendingByTool.get(tool) ?? []
      list.push(idx)
      pendingByTool.set(tool, list)
    } else if (e.kind === 'tool_result') {
      const tool = String(e.payload?.tool ?? '')
      const callId = String(e.payload?.call_id ?? '')
      let idx: number | undefined
      if (callId && pendingByCallId.has(callId)) {
        idx = pendingByCallId.get(callId)
        pendingByCallId.delete(callId)
      } else {
        const list = pendingByTool.get(tool)
        if (list && list.length > 0) {
          idx = list.shift()
        }
      }
      if (idx === undefined) {
        // Orphan result — represent as its own entry.
        entries.push({
          id: e.id,
          ts: e.ts,
          tool,
          args: null,
          ok: Boolean(e.payload?.ok),
          output: e.payload?.output ?? null,
          error: e.payload?.error ? String(e.payload.error) : null,
        })
        continue
      }
      const target = entries[idx]
      target.ok = Boolean(e.payload?.ok)
      target.output = e.payload?.output ?? null
      target.error = e.payload?.error ? String(e.payload.error) : null
    }
  }
  return entries
}
