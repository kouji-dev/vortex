// Worker SSE hook — opens an EventSource against the task's events endpoint
// and pushes parsed WorkerEvent rows into React state. Auth: SSE has to ride
// a cookie session or an Authorization header. EventSource doesn't allow
// custom headers natively, so we authenticate via cookies in the same
// origin (Vite dev proxies); for cross-origin we fall back to fetch + ReadableStream.

import * as React from 'react'
import { parseSseDataLine } from './workers-logic'
import { workerEventsUrl } from './workers-api'
import { authorizedFetch } from './authorizedFetch'
import type { WorkerEvent } from './workers-types'

export interface UseWorkerEventsOptions {
  /** Cap on retained events to bound memory in long-running streams. */
  maxBuffered?: number
  /** Optional callback fired for every parsed event (for terminal echo, etc). */
  onEvent?: (ev: WorkerEvent) => void
}

interface UseWorkerEventsResult {
  events: WorkerEvent[]
  status: 'idle' | 'connecting' | 'open' | 'closed' | 'error'
  reconnect: () => void
}

/**
 * Subscribe to the SSE event stream for a worker task.
 *
 * Uses ``fetch + ReadableStream`` (not EventSource) so authorizedFetch can
 * attach the bearer token. Reconnects automatically with exponential backoff.
 */
export function useWorkerEvents(
  taskId: string | null,
  opts: UseWorkerEventsOptions = {},
): UseWorkerEventsResult {
  const max = opts.maxBuffered ?? 2000
  const [events, setEvents] = React.useState<WorkerEvent[]>([])
  const [status, setStatus] = React.useState<UseWorkerEventsResult['status']>('idle')
  const onEventRef = React.useRef(opts.onEvent)
  onEventRef.current = opts.onEvent
  const tickRef = React.useRef(0)

  const reconnect = React.useCallback(() => {
    tickRef.current += 1
    setEvents([])
  }, [])

  React.useEffect(() => {
    if (!taskId) {
      setStatus('idle')
      return
    }
    const tick = tickRef.current
    const ctrl = new AbortController()
    let cancelled = false
    setStatus('connecting')

    const run = async () => {
      try {
        const res = await authorizedFetch(workerEventsUrl(taskId), {
          method: 'GET',
          headers: { Accept: 'text/event-stream' },
          signal: ctrl.signal,
        })
        if (!res.ok || !res.body) {
          setStatus('error')
          return
        }
        setStatus('open')
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (!cancelled) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          // SSE records are separated by blank line.
          let idx: number
          while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const block = buffer.slice(0, idx)
            buffer = buffer.slice(idx + 2)
            for (const line of block.split('\n')) {
              const ev = parseSseDataLine(line)
              if (!ev) continue
              if (tickRef.current !== tick) return
              setEvents((prev) => {
                const next = prev.length >= max ? prev.slice(-max + 1) : prev.slice()
                next.push(ev)
                return next
              })
              if (onEventRef.current) onEventRef.current(ev)
            }
          }
        }
        if (!cancelled) setStatus('closed')
      } catch (e) {
        if (!cancelled) setStatus('error')
      }
    }

    void run()
    return () => {
      cancelled = true
      ctrl.abort()
    }
  }, [taskId, max])

  return { events, status, reconnect }
}
