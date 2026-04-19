/**
 * useStream — raw SSE streaming hook.
 *
 * Handles only the fetch → parse → state lifecycle. No knowledge of
 * conversation management, model selection, or navigation.
 */
import * as React from 'react'
import type { QueryClient } from '@tanstack/react-query'
import type { ChatMessage, StreamThreadItem } from '~/lib/chat-types'
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
  streamThreadItems: StreamThreadItem[]
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
  const [streamThreadItems, setStreamThreadItems] = React.useState<StreamThreadItem[]>([])
  const [sendError, setSendError] = React.useState<string | null>(null)

  const abortRef = React.useRef<AbortController | null>(null)
  const lastBodyRef = React.useRef<Record<string, unknown> | null>(null)
  const hadSseErrorRef = React.useRef(false)
  const localItemsRef = React.useRef<StreamThreadItem[]>([])

  // Reset visible stream state when switching conversations.
  React.useEffect(() => {
    setStreamThreadItems([])
    setStreamingText('')
    setSendError(null)
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
    setStreamThreadItems([])
    localItemsRef.current = []

    // Optimistic user message so the UI shows the message instantly.
    const userContent = (body.content as string | undefined)?.trim() ?? ''
    if (userContent && body.regenerate_after_message_id == null) {
      await qc.cancelQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })
      qc.setQueryData(
        queryKeys.conversationMessagesTail(conversationId),
        (old: ChatMessage[] | undefined): ChatMessage[] => [
          ...(old ?? []).filter(m => m.id !== -1),
          {
            id: -1,
            conversation_id: conversationId,
            role: 'user',
            content: userContent,
            created_at: new Date().toISOString(),
            extra: null,
          },
        ],
      )
    }

    let streamReachedTerminal = false
    let assembled = ''
    let doneMessageId: number | null = null

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
        for (const ev of events) {
          const e = ev as {
            type?: string; text?: string; detail?: string; message_id?: number
            item?: {
              uid?: string; kind?: string; query?: string; count?: number
              tool?: string; params?: Record<string, string>
              result_snippet?: string; sources?: { kb_name: string; chunks_used: number }[]
              status?: string
            }
          }

          if (e.type === 'item_start') {
            const item = e.item ?? {}
            const uid = (item.uid as string) ?? randomUUID()
            setStreamThreadItems(prev => {
              let next = prev
              if (item.kind === 'memory')
                next = [...prev, { uid, kind: 'memory', count: item.count ?? 0, status: 'running' }]
              else if (item.kind === 'web_search')
                next = [...prev, { uid, kind: 'web_search', query: item.query ?? '', status: 'running' }]
              else if (item.kind === 'fetch_webpage')
                next = [...prev, { uid, kind: 'fetch_webpage', url: item.params?.url ?? '', status: 'running' }]
              else if (item.kind === 'kb_search')
                next = [...prev, { uid, kind: 'kb_search', query: item.query ?? '', status: 'running' }]
              else if (item.kind === 'tool_call')
                next = [...prev, { uid, kind: 'tool_call', tool: item.tool ?? '', params: item.params ?? {}, status: 'running' }]
              localItemsRef.current = next
              return next
            })
          }

          if (e.type === 'item_done') {
            const item = e.item ?? {}
            setStreamThreadItems(prev => {
              const idx = prev.findIndex(it => it.uid === item.uid)
              if (idx === -1) return prev
              const next = prev.map((it, i) => {
                if (i !== idx) return it
                const { status: _s, ...fields } = item as Record<string, unknown>
                return { ...it, ...fields, status: 'done' as const }
              })
              localItemsRef.current = next
              return next
            })
          }

          if (e.type === 'delta' && e.text) {
            assembled += e.text
            setStreamingText(assembled)
          }
          if (e.type === 'error') {
            hadSseErrorRef.current = true
            setSendError(
              typeof e.detail === 'string' && e.detail.trim()
                ? e.detail
                : 'The assistant returned an error.',
            )
          }
          if (e.type === 'done') {
            streamReachedTerminal = true
            doneMessageId = typeof e.message_id === 'number' ? e.message_id : null
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
      setStreamThreadItems([])
    } finally {
      if (abortRef.current === ac) abortRef.current = null
      setStreaming(false)
      setStreamingText('')
      // Clear live stream items immediately — the assembled message written below
      // (via setQueryData) may already carry persisted stream_items, so we must
      // remove the live chips in the same synchronous block to avoid duplicates.
      setStreamThreadItems([])

      // Write the assembled response directly into the cache. This is authoritative
      // — no need to invalidate and refetch conversationMessagesTail.
      if (doneMessageId != null) {
        const updates: ChatMessage[] = []
        if (userContent && body.regenerate_after_message_id == null) {
          updates.push({
            id: doneMessageId - 1,
            conversation_id: conversationId,
            role: 'user',
            content: userContent,
            created_at: new Date(Date.now() - 1000).toISOString(),
            extra: null,
          })
        }
        const finalItems = localItemsRef.current
        updates.push({
          id: doneMessageId,
          conversation_id: conversationId,
          role: 'assistant',
          content: assembled,
          created_at: new Date().toISOString(),
          extra: finalItems.length > 0 ? { stream_items: finalItems } : null,
        })
        qc.setQueryData(
          queryKeys.conversationMessagesTail(conversationId),
          (old: ChatMessage[] | undefined): ChatMessage[] => [
            ...(old ?? []).filter(m => m.id !== -1),
            ...updates,
          ],
        )
      } else {
        // No doneMessageId means the stream was cut short — fall back to a refetch.
        void qc.invalidateQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })
      }
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
    streamThreadItems,
    sendError,
    setSendError,
    runStream,
    stopStream,
    retryStream,
    lastStreamBodyRef: lastBodyRef,
  }
}
