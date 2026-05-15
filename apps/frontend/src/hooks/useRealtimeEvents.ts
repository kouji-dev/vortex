import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { Conversation } from '~/lib/chat-types'
import { queryKeys } from '~/lib/queryKeys'

type SsePayload = { event: string; data: Record<string, unknown> }

function parseSseBlocks(buf: string): { events: SsePayload[]; rest: string } {
  const events: SsePayload[] = []
  const blocks = buf.split(/\r?\n\r?\n/)
  const rest = blocks.pop() ?? ''
  for (const block of blocks) {
    if (!block.trim()) continue
    let eventName = ''
    const dataLines: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith(':')) continue // SSE comment / heartbeat
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!eventName || dataLines.length === 0) continue
    try {
      events.push({ event: eventName, data: JSON.parse(dataLines.join('\n')) })
    } catch {
      // Skip malformed payloads
    }
  }
  return { events, rest }
}

/**
 * Opens a single global SSE connection to /api/events for the authenticated
 * user. Currently handles ``conversation_title_changed`` to keep the sidebar
 * + thread header in sync without a manual refetch when the server
 * auto-titles a conversation.
 *
 * Re-connects with exponential backoff on disconnect. No-op when ``enabled``
 * is false (e.g. before auth, during SSR).
 */
export function useRealtimeEvents(enabled: boolean) {
  const qc = useQueryClient()
  const apiBase = getApiBase()

  React.useEffect(() => {
    if (!enabled) return
    if (typeof window === 'undefined') return

    let cancelled = false
    let backoffMs = 1000
    let abort: AbortController | null = null

    const run = async () => {
      while (!cancelled) {
        abort = new AbortController()
        try {
          const res = await fetch(`${apiBase}/api/events`, {
            method: 'GET',
            headers: {
              Accept: 'text/event-stream',
              ...(await getAuthHeaders()),
            },
            signal: abort.signal,
          })
          if (!res.ok || !res.body) throw new Error(`SSE ${res.status}`)

          backoffMs = 1000 // reset after a successful connect
          const reader = res.body.getReader()
          const dec = new TextDecoder()
          let buf = ''
          while (!cancelled) {
            const { value, done } = await reader.read()
            if (done) break
            buf += dec.decode(value, { stream: true })
            const { events, rest } = parseSseBlocks(buf)
            buf = rest
            for (const ev of events) handleEvent(qc, ev)
          }
        } catch (err) {
          if (cancelled) return
          if (err instanceof DOMException && err.name === 'AbortError') return
          // Fall through to backoff + reconnect.
        }
        if (cancelled) return
        await new Promise((r) => setTimeout(r, backoffMs))
        backoffMs = Math.min(backoffMs * 2, 30_000)
      }
    }
    void run()

    return () => {
      cancelled = true
      abort?.abort()
    }
  }, [enabled, apiBase, qc])
}

function handleEvent(qc: ReturnType<typeof useQueryClient>, ev: SsePayload) {
  switch (ev.event) {
    case 'ready':
      return
    case 'conversation_title_changed': {
      const conversationId = Number(ev.data.conversation_id)
      const title = String(ev.data.title ?? '')
      if (!Number.isFinite(conversationId) || !title) return
      qc.setQueryData<Conversation | undefined>(
        queryKeys.conversation(conversationId),
        (prev) => (prev ? { ...prev, title } : prev),
      )
      qc.setQueryData<Conversation[] | undefined>(
        queryKeys.conversations(),
        (prev) =>
          prev
            ? prev.map((c) => (c.id === conversationId ? { ...c, title } : c))
            : prev,
      )
      return
    }
    default:
      return
  }
}
