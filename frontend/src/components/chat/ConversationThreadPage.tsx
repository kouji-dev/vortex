import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from '@tanstack/react-router'
import { Copy } from 'lucide-react'
import * as React from 'react'

import {
  ChatComposerDock,
  resolveSelectedCatalogModel,
  type CapabilityKey,
} from '~/components/chat/ChatComposerDock'
import { KbPickerDialog } from '~/components/knowledge-bases/KbPickerDialog'
import { KbsToolbarButton } from '~/components/knowledge-bases/KbsToolbarButton'
import { MessageKbIndicator } from '~/components/knowledge-bases/MessageKbIndicator'
import { EmptyConversationState } from '~/components/chat/EmptyConversationState'
import { MarkdownMessage } from '~/components/chat/MarkdownMessage'
import type { SessionModelTuning } from '~/components/chat/ModelTuningModal'
import { defaultTuningFromCatalog } from '~/components/chat/ModelTuningModal'
import { useCatalogModelsQuery } from '~/hooks/useCatalogModelsQuery'
import { useConversationMessagesTailQuery } from '~/hooks/useConversationMessagesTailQuery'
import { useConversationQuery } from '~/hooks/useConversationQuery'
import { getApiBase } from '~/lib/api-base'
import {
  DEFAULT_CAPABILITIES,
  type CapabilityToggles,
  type ChatMessage,
  type Conversation,
  type ConversationSettings,
  type UsedKbEntry,
} from '~/lib/chat-types'
import { isConversationNotFoundError } from '~/lib/conversation-not-found'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  knowledgeBaseListFromResponse,
  parseKnowledgeBasesListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'
import { parseSseBlocks } from '~/lib/sse-parse'
import { useConversationsOutlet } from '~/contexts/ConversationsOutletContext'

const MESSAGES_LIMIT = 100

/** Distance from scroll bottom (px) treated as "following" the thread — auto-scroll SSE only then. */
const THREAD_BOTTOM_STICKY_PX = 80

function isPersistedStreamErrorMessage(content: string): boolean {
  return content.trimStart().startsWith('**Error:**')
}

export type ConversationThreadPageProps = {
  /** `null` = composer on `/chat/conversations` before a thread exists in the API. */
  conversationId: number | null
}

export function ConversationThreadPage({ conversationId }: ConversationThreadPageProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()
  const apiBase = getApiBase()
  const { composeDraft, setComposeDraft, chatStarters, chatStartersFetched } =
    useConversationsOutlet()
  const [streamingText, setStreamingText] = React.useState('')
  const [streaming, setStreaming] = React.useState(false)
  const [sendError, setSendError] = React.useState<string | null>(null)
  const [kbPickerOpen, setKbPickerOpen] = React.useState(false)
  const [modelDraft, setModelDraft] = React.useState('')
  const [olderMessages, setOlderMessages] = React.useState<ChatMessage[]>([])
  const [canLoadOlder, setCanLoadOlder] = React.useState(false)
  const [loadingOlder, setLoadingOlder] = React.useState(false)
  const messagesScrollRef = React.useRef<HTMLDivElement>(null)
  const scrollThreadRafRef = React.useRef<number | null>(null)
  const wasStreamingRef = React.useRef(false)
  const stickToBottomRef = React.useRef(true)
  const streamAbortRef = React.useRef<AbortController | null>(null)
  const isComposerMode = conversationId == null
  const [draftModel, setDraftModel] = React.useState('')
  const [draftCaps, setDraftCaps] = React.useState<CapabilityToggles>({
    ...DEFAULT_CAPABILITIES,
  })
  const [sessionTuning, setSessionTuning] = React.useState<SessionModelTuning>(() =>
    defaultTuningFromCatalog(null),
  )

  const convQ = useConversationQuery(conversationId)
  const catalogQ = useCatalogModelsQuery()

  const kbListQ = useQuery({
    queryKey: queryKeys.knowledgeBases(),
    queryFn: async () => {
      const res = await fetch(`${getApiBase()}/api/knowledge-bases`, {
        headers: await getAuthHeaders(),
      })
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseKnowledgeBasesListJson)
    },
    enabled: !isComposerMode,
  })

  const knowledge_base_ids = convQ.data?.knowledge_base_ids ?? []
  const activeKbs = (kbListQ.data ?? [])
    .filter((kb) => knowledge_base_ids.includes(kb.id))
    .map((kb) => ({ id: kb.id, name: kb.name, document_count: kb.document_count }))

  const activeChatModel = isComposerMode ? draftModel : modelDraft
  const selectedCatalogModel = resolveSelectedCatalogModel(catalogQ.data, activeChatModel)

  React.useEffect(() => {
    setSessionTuning(defaultTuningFromCatalog(selectedCatalogModel))
  }, [selectedCatalogModel?.id, activeChatModel])

  React.useEffect(() => {
    if (convQ.data) {
      setModelDraft(convQ.data.model ?? '')
    }
  }, [convQ.data?.id, convQ.data?.model])

  React.useEffect(() => {
    setOlderMessages([])
    setCanLoadOlder(false)
  }, [conversationId])

  React.useEffect(() => {
    stickToBottomRef.current = true
  }, [conversationId])

  const conversationMissing =
    !isComposerMode &&
    convQ.isError &&
    isConversationNotFoundError(String((convQ.error as Error)?.message ?? ''))

  React.useEffect(() => {
    if (!conversationMissing) return
    void navigate({ to: '/chat/conversations', replace: true })
  }, [conversationMissing, navigate])

  const tailQ = useConversationMessagesTailQuery(conversationId, MESSAGES_LIMIT)

  React.useEffect(() => {
    if (tailQ.data == null) return
    if (olderMessages.length === 0) {
      setCanLoadOlder(tailQ.data.length >= MESSAGES_LIMIT)
    }
  }, [tailQ.data, conversationId, olderMessages.length])

  const visibleMessages = React.useMemo(
    () => [...olderMessages, ...(tailQ.data ?? [])],
    [olderMessages, tailQ.data],
  )

  const showEmptyHub =
    !streaming &&
    visibleMessages.length === 0 &&
    (isComposerMode || (convQ.data != null && !tailQ.isPending))

  const threadMessagesLoading =
    !isComposerMode &&
    !streaming &&
    visibleMessages.length === 0 &&
    (convQ.isPending || tailQ.isPending)

  const patchConv = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      if (conversationId == null) throw new Error('No conversation')
      const res = await fetch(`${apiBase}/api/chat/conversations/${conversationId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<Conversation>
    },
    onSuccess: (data) => {
      if (conversationId == null) return
      void qc.setQueryData(queryKeys.conversation(conversationId), data)
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
    },
  })

  const deleteConv = useMutation({
    mutationFn: async () => {
      if (conversationId == null) throw new Error('No conversation')
      const res = await fetch(`${apiBase}/api/chat/conversations/${conversationId}`, {
        method: 'DELETE',
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
      void navigate({ to: '/chat/conversations' })
    },
  })

  const caps: CapabilityToggles = isComposerMode
    ? draftCaps
    : (convQ.data?.settings?.capabilities ?? DEFAULT_CAPABILITIES)

  const setCapabilities = (next: CapabilityToggles) => {
    if (isComposerMode) {
      setDraftCaps(next)
      return
    }
    const prevSettings: ConversationSettings = convQ.data?.settings ?? {}
    patchConv.mutate({
      settings: {
        ...prevSettings,
        capabilities: next,
      },
    })
  }

  const commitChatModel = (m: string) => {
    const trimmed = m.trim()
    if (isComposerMode) return
    const current = convQ.data?.model ?? ''
    if (trimmed === current) return
    patchConv.mutate({ model: trimmed || null })
  }

  const toggleCapability = (key: CapabilityKey) => {
    setCapabilities({
      ...caps,
      [key]: !caps[key],
    })
  }

  const loadOlder = async () => {
    if (conversationId == null) return
    const first = visibleMessages[0]
    if (!first || loadingOlder) return
    setLoadingOlder(true)
    try {
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/messages?limit=${MESSAGES_LIMIT}&recent=true&before_id=${first.id}`,
        { headers: await getAuthHeaders() },
      )
      if (!res.ok) return
      const chunk = (await res.json()) as ChatMessage[]
      if (chunk.length === 0) {
        setCanLoadOlder(false)
        return
      }
      if (chunk.length < MESSAGES_LIMIT) setCanLoadOlder(false)
      setOlderMessages((prev) => [...chunk, ...prev])
    } finally {
      setLoadingOlder(false)
    }
  }

  const stopStream = () => {
    streamAbortRef.current?.abort()
  }

  const runStream = async (body: Record<string, unknown>) => {
    if (conversationId == null || !Number.isFinite(conversationId)) return
    streamAbortRef.current?.abort()
    const ac = new AbortController()
    streamAbortRef.current = ac
    setSendError(null)
    setStreaming(true)
    setStreamingText('')
    let streamReachedTerminal = false
    let assembled = ''
    try {
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/messages/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify(body),
          signal: ac.signal,
        },
      )
      if (!res.ok) {
        const err = await res.text()
        setSendError(err || `HTTP ${res.status}`)
        return
      }
      const reader = res.body?.getReader()
      if (!reader) {
        setSendError('No response body')
        return
      }
      const dec = new TextDecoder()
      let buf = ''
      const applyEvents = (events: unknown[]) => {
        for (const ev of events) {
          const e = ev as { type?: string; text?: string; detail?: string }
          if (e.type === 'delta' && e.text) {
            assembled += e.text
            setStreamingText(assembled)
          }
          if (e.type === 'error') {
            /* Server persists this as an assistant row; refetch in `finally`. */
          }
          if (e.type === 'done') {
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
    } finally {
      if (streamAbortRef.current === ac) streamAbortRef.current = null
      setStreaming(false)
      setStreamingText('')
      setOlderMessages([])
      void qc.invalidateQueries({
        queryKey: queryKeys.conversationMessagesTail(conversationId),
      })
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
      void qc.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) })
    }
    if (streamReachedTerminal && body.regenerate_after_message_id == null) {
      setComposeDraft('')
    }
  }

  const runStreamRef = React.useRef(runStream)
  runStreamRef.current = runStream

  const pendingStream = location.state?.pendingStream

  React.useLayoutEffect(() => {
    if (conversationId == null) return
    const pending = pendingStream
    if (!pending?.content?.trim() || !pending.bootstrapId) return
    const key = `aip-bs-${pending.bootstrapId}`
    if (sessionStorage.getItem(key)) return
    sessionStorage.setItem(key, '1')

    const body: Record<string, unknown> = {
      content: pending.content.trim(),
      use_rag: pending.use_rag,
    }
    if (pending.model) body.model = pending.model

    void (async () => {
      try {
        await runStreamRef.current(body)
      } finally {
        void navigate({
          to: '/chat/conversations/$id',
          params: { id: String(conversationId) },
          replace: true,
          state: {},
        })
      }
    })()
  }, [conversationId, pendingStream?.bootstrapId, pendingStream?.content, navigate])

  const sendStream = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return

    if (isComposerMode) {
      setSendError(null)
      try {
        const settings: ConversationSettings = {
          capabilities: draftCaps,
        }
        const res = await fetch(`${apiBase}/api/chat/conversations`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify({
            title: null,
            assistant_id: null,
            model: draftModel.trim() || null,
            settings,
          }),
        })
        if (!res.ok) {
          setSendError(await res.text())
          return
        }
        const created = (await res.json()) as { id: number }
        void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
        const modelParam = draftModel.trim() || undefined
        const bootstrapId = crypto.randomUUID()
        setComposeDraft('')
        void navigate({
          to: '/chat/conversations/$id',
          params: { id: String(created.id) },
          replace: true,
          state: {
            pendingStream: {
              bootstrapId,
              content: trimmed,
              use_rag: false,
              ...(modelParam ? { model: modelParam } : {}),
            },
          },
        })
      } catch (e) {
        setSendError(e instanceof Error ? e.message : 'Could not start conversation')
      }
      return
    }

    const modelParam = modelDraft.trim() || undefined
    const body: Record<string, unknown> = {
      content: trimmed,
      use_rag: true,
    }
    if (modelParam) body.model = modelParam
    await runStream(body)
  }

  const regenerateAssistantReply = async (assistantMessageId: number) => {
    const modelParam = modelDraft.trim() || undefined
    const body: Record<string, unknown> = {
      content: '',
      regenerate_after_message_id: assistantMessageId,
      use_rag: true,
    }
    if (modelParam) body.model = modelParam
    await runStream(body)
  }

  const scrollThreadToBottom = React.useCallback((behavior: ScrollBehavior) => {
    const el = messagesScrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior })
  }, [])

  const syncStickToBottomFromScroll = React.useCallback(() => {
    const el = messagesScrollRef.current
    if (!el) return
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    stickToBottomRef.current = gap <= THREAD_BOTTOM_STICKY_PX
  }, [])

  /** Batch scroll to bottom on the messages pane only (no document scroll jank). */
  React.useLayoutEffect(() => {
    if (scrollThreadRafRef.current != null) cancelAnimationFrame(scrollThreadRafRef.current)
    scrollThreadRafRef.current = requestAnimationFrame(() => {
      scrollThreadRafRef.current = null
      if (!stickToBottomRef.current) return
      scrollThreadToBottom('auto')
    })
    return () => {
      if (scrollThreadRafRef.current != null) cancelAnimationFrame(scrollThreadRafRef.current)
    }
  }, [visibleMessages, streamingText, streaming, scrollThreadToBottom])

  /** One gentle settle after the stream ends (DOM updates from refetch). */
  React.useEffect(() => {
    const wasStreaming = wasStreamingRef.current
    wasStreamingRef.current = streaming
    if (!wasStreaming || streaming) return
    if (!stickToBottomRef.current) return
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => scrollThreadToBottom('smooth'))
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [streaming, scrollThreadToBottom])

  if (conversationId != null && !Number.isFinite(conversationId)) {
    return <p className="text-red-600 text-sm">Invalid conversation.</p>
  }

  if (conversationMissing) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        This conversation no longer exists. Opening a new chat…
      </p>
    )
  }

  if (!isComposerMode && convQ.isError) {
    return (
      <p className="text-red-600 text-sm">
        {(convQ.error as Error).message || 'Could not load conversation.'}
      </p>
    )
  }

  const surfaceThemed =
    'border-neutral-200 bg-neutral-50 text-neutral-900 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-100'
  const inputThemed =
    'border-neutral-300 bg-white text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100'
  const lastMessageId = visibleMessages.at(-1)?.id

  const displayTitle = isComposerMode
    ? 'New conversation'
    : convQ.data?.title?.trim()
      ? convQ.data.title
      : 'New conversation'

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
      <header className="shrink-0 flex flex-col gap-1.5 border-b border-neutral-200 pb-2 dark:border-neutral-800 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-0.5">
          <h1 className="truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100 sm:text-base">
            {displayTitle}
          </h1>
          {!isComposerMode && convQ.data?.created_at && (
            <p className="text-xs text-neutral-400">
              Created {formatWhen(convQ.data.created_at)}
            </p>
          )}
        </div>
        {!isComposerMode && (
          <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
            <button
              type="button"
              className="rounded border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
              disabled={deleteConv.isPending}
              onClick={() => {
                if (window.confirm('Delete this conversation and all messages?')) {
                  deleteConv.mutate()
                }
              }}
            >
              Delete
            </button>
          </div>
        )}
      </header>

      {patchConv.isError && (
        <p className="shrink-0 text-sm text-red-600">{(patchConv.error as Error).message}</p>
      )}
      {deleteConv.isError && (
        <p className="shrink-0 text-sm text-red-600">{(deleteConv.error as Error).message}</p>
      )}
      <div
        ref={messagesScrollRef}
        onScroll={syncStickToBottomFromScroll}
        className={`min-h-0 w-full min-w-0 flex-1 overflow-y-auto overflow-x-hidden scroll-pb-4 overscroll-contain rounded-xl border p-4 sm:p-5 ${surfaceThemed}`}
      >
        {canLoadOlder && visibleMessages.length > 0 && (
          <div className="mb-3 flex justify-center">
            <button
              type="button"
              className="text-xs text-blue-600 underline decoration-dotted disabled:opacity-50"
              disabled={loadingOlder || tailQ.isPending}
              onClick={() => void loadOlder()}
            >
              {loadingOlder ? 'Loading…' : 'Load older messages'}
            </button>
          </div>
        )}
        {threadMessagesLoading ? (
          <div className="flex min-h-[min(50dvh,22rem)] w-full flex-col items-center justify-center px-4">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading messages…</p>
          </div>
        ) : showEmptyHub ? (
          <EmptyConversationState
            starters={chatStarters}
            startersFetched={chatStartersFetched}
            setComposeDraft={setComposeDraft}
          />
        ) : (
          <>
        <ul className="flex w-full flex-col gap-5">
          {visibleMessages.map((m) => {
            const isUserSide = m.role === 'user'
            const isSystem = m.role === 'system'
            const isLatestAssistant =
              m.role === 'assistant' && lastMessageId === m.id && !streaming
            const isErrorAssistant =
              m.role === 'assistant' && isPersistedStreamErrorMessage(m.content)
            const roleLabel =
              isErrorAssistant ? 'error' : m.role === 'system' ? 'system' : m.role
            return (
              <li
                key={m.id}
                className={`flex w-full text-sm ${isUserSide ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`rounded-2xl px-4 py-3 ${
                    isUserSide
                      ? 'ml-auto max-w-[min(92%,42rem)] bg-neutral-100/95 text-neutral-900 dark:bg-neutral-800/95 dark:text-neutral-100'
                      : isSystem
                        ? 'w-full max-w-none bg-neutral-100/70 text-neutral-800 dark:bg-neutral-800/50 dark:text-neutral-200'
                        : isErrorAssistant
                          ? 'w-full max-w-none bg-red-50/90 dark:bg-red-950/35'
                          : 'w-full max-w-none bg-white/90 dark:bg-neutral-900/75'
                  }`}
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wide ${
                        isErrorAssistant
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-neutral-500 dark:text-neutral-400'
                      }`}
                    >
                      {roleLabel}
                    </span>
                    <div className="flex items-center gap-1">
                      {m.role === 'assistant' && (
                        <MessageKbIndicator
                          usedKbs={(m.extra?.used_kbs as UsedKbEntry[] | undefined) ?? []}
                        />
                      )}
                      <time
                        className="text-[10px] tabular-nums text-neutral-400 dark:text-neutral-500"
                        dateTime={m.created_at}
                        title={m.created_at}
                      >
                        {formatWhen(m.created_at)}
                      </time>
                      <button
                        type="button"
                        className="rounded p-1 text-neutral-500 transition-colors hover:bg-neutral-200/70 disabled:opacity-40 dark:text-neutral-400 dark:hover:bg-neutral-700/60"
                        disabled={streaming}
                        aria-label="Copy message"
                        onClick={() => void copyToClipboard(m.content)}
                      >
                        <Copy className="size-3.5" strokeWidth={2} />
                      </button>
                      {isLatestAssistant && (
                        <button
                          type="button"
                          className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 underline decoration-dotted decoration-neutral-400/80 underline-offset-2 hover:text-neutral-900 disabled:opacity-40 dark:text-neutral-400 dark:decoration-neutral-500 dark:hover:text-neutral-200"
                          disabled={streaming}
                          onClick={() => void regenerateAssistantReply(m.id)}
                        >
                          Regenerate
                        </button>
                      )}
                    </div>
                  </div>
                  <div
                    className={
                      isUserSide
                        ? '[&_blockquote]:border-neutral-300 [&_blockquote]:text-neutral-600 dark:[&_blockquote]:border-neutral-600 dark:[&_blockquote]:text-neutral-400 [&_pre]:border-neutral-200 [&_pre]:bg-neutral-200/60 dark:[&_pre]:border-neutral-700 dark:[&_pre]:bg-neutral-950/80'
                        : ''
                    }
                  >
                    <MarkdownMessage
                      content={m.content}
                      className={
                        m.role === 'assistant' && isErrorAssistant
                          ? 'text-red-800 dark:text-red-200'
                          : m.role === 'assistant'
                            ? 'text-neutral-900 dark:text-neutral-100'
                            : isUserSide
                              ? 'text-neutral-900 dark:text-neutral-100'
                              : 'text-neutral-800 dark:text-neutral-200'
                      }
                    />
                  </div>
                  {m.extra != null && Object.keys(m.extra).length > 0 && (
                    <details className="mt-2 text-xs">
                      <summary className="cursor-pointer text-neutral-500 dark:text-neutral-400">
                        Message metadata
                      </summary>
                      <pre
                        className={`mt-1 max-h-40 overflow-auto rounded border p-2 font-mono ${
                          isUserSide
                            ? 'border-neutral-200 bg-neutral-200/40 text-neutral-800 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-300'
                            : 'border-neutral-200 bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-950'
                        }`}
                      >
                        {JSON.stringify(m.extra, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
        {streaming && (
          <div className="mt-1 w-full">
            <div className="stream-surface-breathe w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  assistant
                </span>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-neutral-400">streaming…</span>
                  <button
                    type="button"
                    className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 underline decoration-dotted dark:text-red-400"
                    onClick={stopStream}
                  >
                    Stop
                  </button>
                </div>
              </div>
              {streamingText ? (
                <MarkdownMessage
                  content={streamingText}
                  streaming
                  className="text-neutral-900 dark:text-neutral-100"
                />
              ) : (
                <p className="flex items-center gap-2 text-sm text-neutral-400">
                  <span className="inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
                  Waiting for tokens…
                </p>
              )}
            </div>
          </div>
        )}
          </>
        )}
      </div>

      {sendError && (
        <div
          className="shrink-0 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200"
          role="alert"
        >
          {sendError}
        </div>
      )}

      {!isComposerMode && conversationId != null && (
        <KbPickerDialog
          conversationId={conversationId}
          open={kbPickerOpen}
          onClose={() => setKbPickerOpen(false)}
        />
      )}

      <div className="w-full shrink-0">
      <ChatComposerDock
        models={catalogQ.data}
        modelsPending={catalogQ.isPending}
        modelsError={catalogQ.error as Error | null}
        chatModel={activeChatModel}
        onSelectChatModel={(id) => {
          if (isComposerMode) setDraftModel(id)
          else setModelDraft(id)
        }}
        onCommitChatModel={isComposerMode ? undefined : commitChatModel}
        modelSelectDisabled={!isComposerMode && (convQ.isPending || patchConv.isPending)}
        capabilities={caps}
        onToggleCapability={toggleCapability}
        capabilityDisabled={!isComposerMode && (patchConv.isPending || convQ.isPending)}
        composeDraft={composeDraft}
        setComposeDraft={setComposeDraft}
        onSubmit={() => {
          const t = composeDraft.trim()
          if (t && !streaming) void sendStream(t)
        }}
        streaming={streaming}
        onStop={stopStream}
        inputThemed={inputThemed}
        kbSlot={
          !isComposerMode && conversationId != null ? (
            <KbsToolbarButton
              activeCount={knowledge_base_ids.length}
              activeKbs={activeKbs}
              onOpen={() => setKbPickerOpen(true)}
            />
          ) : undefined
        }
        selectedCatalogModel={selectedCatalogModel}
        tuning={sessionTuning}
        onTuningChange={setSessionTuning}
      />
      </div>
    </div>
  )
}

function formatWhen(iso: string) {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    window.prompt('Copy:', text)
  }
}
