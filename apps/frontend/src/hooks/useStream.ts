/**
 * useStream — raw SSE streaming hook (ThreadItem-based).
 *
 * Handles only the fetch → parse → state lifecycle. No knowledge of
 * conversation management, model selection, or navigation.
 */
import * as React from 'react'
import type { QueryClient } from '@tanstack/react-query'
import type {
  AssistantTextPayload,
  SseEvent,
  ThreadItem,
  ThreadItemBase,
} from '~/lib/chat-types'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { queryKeys } from '~/lib/queryKeys'
import { parseSseBlocks } from '~/lib/sse-parse'

const randomUUID = (): string =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
      })

export type StreamRunCallbacks = {
  /** Called once in the finally block regardless of outcome. */
  onFinally?: () => void
  /** Called when stream reaches a `done` event with no SSE error. */
  onSuccess?: () => void
}

export type UseStreamReturn = {
  streaming: boolean
  streamingText: string
  streamItems: ThreadItem[]
  sendError: string | null
  setSendError: React.Dispatch<React.SetStateAction<string | null>>
  /** Run the stream. Resolves when the fetch + SSE loop is complete. */
  runStream: (body: Record<string, unknown>, cbs?: StreamRunCallbacks) => Promise<void>
  stopStream: () => void
  /** Re-run the last body. No-op if nothing has been streamed yet. */
  retryStream: (cbs?: StreamRunCallbacks) => Promise<void>
  /** Ref to the last streamed request body (used to expose a retry button). */
  lastStreamBodyRef: React.RefObject<Record<string, unknown> | null>
}

export function useStream({
  conversationId,
  apiBase,
  queryClient: qc,
}: {
  conversationId: number | null
  apiBase: string
  queryClient: QueryClient
}): UseStreamReturn {
  const [streaming, setStreaming] = React.useState(false)
  const [streamingText, setStreamingText] = React.useState('')
  const [streamItems, setStreamItems] = React.useState<ThreadItem[]>([])
  const [sendError, setSendError] = React.useState<string | null>(null)

  const abortRef = React.useRef<AbortController | null>(null)
  const lastBodyRef = React.useRef<Record<string, unknown> | null>(null)
  const hadSseErrorRef = React.useRef(false)
  // Items tracked by backend id; newer versions replace older ones.
  const liveItemsRef = React.useRef<Map<number, ThreadItem>>(new Map())

  // Reset visible stream state when switching conversations.
  React.useEffect(() => {
    setStreamItems([])
    setStreamingText('')
    setSendError(null)
    liveItemsRef.current = new Map()
  }, [conversationId])

  const stopStream = React.useCallback(() => {
    abortRef.current?.abort()
  }, [])

  // Stable ref so callers that close over runStream always get the latest version.
  const runStreamImpl = React.useCallback(async (
    body: Record<string, unknown>,
    cbs?: StreamRunCallbacks,
  ) => {
    if (conversationId == null || !Number.isFinite(conversationId)) return

    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    lastBodyRef.current = body
    hadSseErrorRef.current = false

    setSendError(null)
    setStreaming(true)
    setStreamingText('')
    setStreamItems([])
    liveItemsRef.current = new Map()

    // Optimistic user message so the UI shows the message instantly.
    const userContent = (body.content as string | undefined)?.trim() ?? ''
    if (userContent && body.regenerate_after_message_id == null) {
      await qc.cancelQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })
      const fakeUserItem: ThreadItem = {
        id: -1,
        thread_id: conversationId,
        turn_id: randomUUID(),
        kind: 'user_message',
        role: 'user',
        status: 'done',
        provider: null,
        model: null,
        cost_usd: null,
        cost_estimated: false,
        latency_ms: null,
        parent_item_id: null,
        started_at: null,
        finished_at: null,
        created_at: new Date().toISOString(),
        data: { text: userContent, attachments: [] },
      }
      qc.setQueryData(
        queryKeys.conversationMessagesTail(conversationId),
        (old: ThreadItem[] | undefined): ThreadItem[] => [
          ...(old ?? []).filter((i) => i.id !== -1),
          fakeUserItem,
        ],
      )
    }

    let streamReachedTerminal = false

    try {
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/messages/stream`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(await getAuthHeaders()) },
          body: JSON.stringify(body),
          signal: ac.signal,
        },
      )
      if (!res.ok) {
        setSendError((await res.text()) || `HTTP ${res.status}`)
        return
      }
      const reader = res.body?.getReader()
      if (!reader) { setSendError('No response body'); return }

      const dec = new TextDecoder()
      let buf = ''

      const applyEvents = (events: unknown[]) => {
        for (const raw of events) {
          const e = raw as SseEvent

          if (e.event_type === 'item') {
            const item = e.item
            liveItemsRef.current.set(item.id, item)
            const items = Array.from(liveItemsRef.current.values())
            setStreamItems(items)

            // Update streaming text from the latest assistant_text item.
            const textItem = [...items]
              .reverse()
              .find((i) => i.kind === 'assistant_text') as
                | (ThreadItemBase & { kind: 'assistant_text'; data: AssistantTextPayload })
                | undefined
            if (textItem) setStreamingText(textItem.data.text)
          } else if (e.event_type === 'error') {
            hadSseErrorRef.current = true
            setSendError(e.error?.message || 'The assistant returned an error.')
          } else if (e.event_type === 'done') {
            streamReachedTerminal = true
          }
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const { events, rest } = parseSseBlocks(buf)
        buf = rest
        applyEvents(events)
      }
      applyEvents(parseSseBlocks(buf + '\n\n').events)
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        setSendError(null)
      } else {
        setSendError(e instanceof Error ? e.message : 'Stream failed')
      }
      setStreamItems([])
    } finally {
      if (abortRef.current === ac) abortRef.current = null
      setStreaming(false)
      setStreamingText('')
      // Clear live stream items synchronously — the invalidation below refetches
      // persisted ThreadItem[] which will drive the post-stream render.
      setStreamItems([])
      liveItemsRef.current = new Map()

      // The backend is authoritative for persisted ThreadItems — invalidate the
      // tail so the next render shows fully-persisted items with costs/usage.
      void qc.invalidateQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })
      // Refresh the conversation title + sidebar list.
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
      void qc.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) })

      cbs?.onFinally?.()
      if (streamReachedTerminal && !hadSseErrorRef.current) {
        cbs?.onSuccess?.()
      }
    }
  }, [conversationId, apiBase, qc])

  // Keep a stable ref so callers don't need to re-close over the latest function.
  const runStreamRef = React.useRef(runStreamImpl)
  runStreamRef.current = runStreamImpl

  const runStream = React.useCallback(
    (body: Record<string, unknown>, cbs?: StreamRunCallbacks) => runStreamRef.current(body, cbs),
    [],
  )

  const retryStream = React.useCallback(
    (cbs?: StreamRunCallbacks) => {
      if (lastBodyRef.current) return runStream(lastBodyRef.current, cbs)
      return Promise.resolve()
    },
    [runStream],
  )

  return {
    streaming,
    streamingText,
    streamItems,
    sendError,
    setSendError,
    runStream,
    stopStream,
    retryStream,
    lastStreamBodyRef: lastBodyRef,
  }
}
