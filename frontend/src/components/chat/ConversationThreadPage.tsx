import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from '@tanstack/react-router'
import { Copy } from 'lucide-react'
import * as React from 'react'
import { flushSync } from 'react-dom'

import {
  ChatComposerDock,
  resolveSelectedCatalogModel,
  type CapabilityKey,
} from '~/components/chat/ChatComposerDock'
import { ChatComposerDockMobile } from '~/components/chat/ChatComposerDockMobile'
import { useIsMobile } from '~/hooks/useIsMobile'
import { KbChatPicker } from '~/components/knowledge-bases/KbChatPicker'
import { MessageKbIndicator } from '~/components/knowledge-bases/MessageKbIndicator'
import { EmptyConversationState } from '~/components/chat/EmptyConversationState'
import { MarkdownMessage } from '~/components/chat/MarkdownMessage'
import { StartersPanel } from '~/components/chat/StartersPanel'
import type { SessionModelTuning } from '~/components/chat/ModelTuningModal'
import { defaultTuningFromCatalog } from '~/components/chat/ModelTuningModal'
import { useChatCapabilityProfileQuery } from '~/hooks/useChatCapabilityProfileQuery'
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
  type StreamItem,
  type ThinkingItem,
  type ToolCallItem,
} from '~/lib/chat-types'
import { isConversationNotFoundError } from '~/lib/conversation-not-found'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { queryKeys } from '~/lib/queryKeys'
import { parseSseBlocks } from '~/lib/sse-parse'
import { useConversationsOutlet } from '~/contexts/ConversationsOutletContext'
import { StreamingThinkingBlock } from '~/components/chat/StreamingThinkingBlock'

const MESSAGES_LIMIT = 100
const MAX_ATTACHMENTS_PER_MESSAGE = 5

/** Distance from scroll bottom (px) treated as "following" the thread — auto-scroll SSE only then. */
const THREAD_BOTTOM_STICKY_PX = 80

function isPersistedStreamErrorMessage(content: string): boolean {
  return content.trimStart().startsWith('**Error:**')
}

function usedKbsFromMessage(m: ChatMessage): UsedKbEntry[] {
  const raw = m.used_kbs ?? m.extra?.used_kbs
  return Array.isArray(raw) ? (raw as UsedKbEntry[]) : []
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
  const [streamItems, setStreamItems] = React.useState<StreamItem[]>([])
  const [thinkingExpanded, setThinkingExpanded] = React.useState(false)
  const [sendError, setSendError] = React.useState<string | null>(null)
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
  const isMobile = useIsMobile()
  const [draftModel, setDraftModel] = React.useState('')
  const [confirmDeleteOpen, setConfirmDeleteOpen] = React.useState(false)
  const [draftCaps, setDraftCaps] = React.useState<CapabilityToggles>({
    ...DEFAULT_CAPABILITIES,
  })
  const [sessionTuning, setSessionTuning] = React.useState<SessionModelTuning>(() =>
    defaultTuningFromCatalog(null),
  )
  const [draftKbIds, setDraftKbIds] = React.useState<number[]>([])
  const [pendingAttachments, setPendingAttachments] = React.useState<
    { id: number; name: string }[]
  >([])
  const [pendingComposerFiles, setPendingComposerFiles] = React.useState<File[]>([])
  const lastStreamBodyRef = React.useRef<Record<string, unknown> | null>(null)
  const streamHadSseErrorRef = React.useRef(false)
  const composerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!isMobile) return
    const vv = window.visualViewport
    if (!vv) return
    const apply = () => {
      const node = composerRef.current
      if (!node) return
      const offsetFromBottom = window.innerHeight - (vv.offsetTop + vv.height)
      node.style.paddingBottom = `${offsetFromBottom}px`
    }
    apply()
    vv.addEventListener('resize', apply)
    vv.addEventListener('scroll', apply)
    return () => {
      vv.removeEventListener('resize', apply)
      vv.removeEventListener('scroll', apply)
      const node = composerRef.current
      if (node) node.style.paddingBottom = ''
    }
  }, [isMobile])

  const convQ = useConversationQuery(conversationId)
  const catalogQ = useCatalogModelsQuery()
  const capProfileQ = useChatCapabilityProfileQuery(true)
  const capabilityDescriptions = React.useMemo(
    () =>
      capProfileQ.data
        ? {
            reflection: capProfileQ.data.reflection.description,
            research: capProfileQ.data.research.description,
            web: capProfileQ.data.web.description,
          }
        : undefined,
    [capProfileQ.data],
  )

  const knowledge_base_ids = convQ.data?.knowledge_base_ids ?? []

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
    setStreamItems([])
    setThinkingExpanded(false)
  }, [conversationId])

  React.useEffect(() => {
    stickToBottomRef.current = true
  }, [conversationId])

  React.useEffect(() => {
    if (conversationId != null) setDraftKbIds([])
  }, [conversationId])

  React.useEffect(() => {
    setPendingAttachments([])
    setPendingComposerFiles([])
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
      setConfirmDeleteOpen(false)
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

  const onLocalFilesChosen = React.useCallback(
    async (files: File[]) => {
      const list = files.slice(0, MAX_ATTACHMENTS_PER_MESSAGE)
      if (isComposerMode) {
        setPendingComposerFiles((p) => [...p, ...list].slice(0, MAX_ATTACHMENTS_PER_MESSAGE))
        return
      }
      if (conversationId == null) return
      const room = MAX_ATTACHMENTS_PER_MESSAGE - pendingAttachments.length
      if (room <= 0) return
      for (const f of list.slice(0, room)) {
        try {
          const fd = new FormData()
          fd.append('file', f)
          const res = await fetch(
            `${apiBase}/api/chat/conversations/${conversationId}/uploads`,
            { method: 'POST', headers: await getAuthHeaders(), body: fd },
          )
          if (!res.ok) {
            setSendError(await res.text())
            return
          }
          const j = (await res.json()) as { id: number; original_filename: string }
          setPendingAttachments((p) =>
            [...p, { id: j.id, name: j.original_filename }].slice(
              0,
              MAX_ATTACHMENTS_PER_MESSAGE,
            ),
          )
        } catch (e) {
          setSendError(e instanceof Error ? e.message : 'Upload failed')
        }
      }
    },
    [apiBase, conversationId, isComposerMode, pendingAttachments.length],
  )

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
    lastStreamBodyRef.current = body
    streamHadSseErrorRef.current = false
    setSendError(null)
    setStreaming(true)
    setStreamingText('')
    setStreamItems([])
    setThinkingExpanded(false)
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
          const e = ev as {
            type?: string
            text?: string
            detail?: string
            item?: {
              kind?: string
              tool?: string
              params?: Record<string, string>
              count?: number
              status?: string
            }
          }

          if (e.type === 'item_start') {
            const item = e.item ?? {}
            if (item.kind === 'thinking') {
              setStreamItems(prev => [...prev, { kind: 'thinking', status: 'running', children: [] }])
              setThinkingExpanded(true)
            } else if (item.kind === 'memory') {
              setStreamItems((prev) => {
                let thinkingIdx = -1
                for (let j = prev.length - 1; j >= 0; j--) {
                  const it = prev[j]
                  if (it.kind === 'thinking' && it.status === 'running') {
                    thinkingIdx = j
                    break
                  }
                }
                if (thinkingIdx === -1) return prev
                return prev.map((si, j) => {
                  if (j !== thinkingIdx || si.kind !== 'thinking') return si
                  return {
                    ...si,
                    children: [
                      ...si.children,
                      {
                        kind: 'memory' as const,
                        count: item.count ?? 0,
                        status: 'running' as const,
                      },
                    ],
                  }
                })
              })
            } else if (item.kind === 'tool_call') {
              setStreamItems((prev) => {
                const toolItem: ToolCallItem = {
                  kind: 'tool_call',
                  tool: item.tool ?? '',
                  params: item.params ?? {},
                  status: 'running',
                }
                let thinkingIdx = -1
                for (let j = prev.length - 1; j >= 0; j--) {
                  const it = prev[j]
                  if (it.kind === 'thinking' && it.status === 'running') {
                    thinkingIdx = j
                    break
                  }
                }
                if (thinkingIdx === -1) {
                  return [...prev, toolItem]
                }
                return prev.map((si, j) => {
                  if (j !== thinkingIdx || si.kind !== 'thinking') return si
                  return {
                    ...si,
                    children: [...si.children, toolItem],
                  }
                })
              })
            }
          }

          if (e.type === 'item_done') {
            const item = e.item ?? {}
            if (item.kind === 'thinking') {
              setStreamItems(prev =>
                prev.map(i =>
                  i.kind === 'thinking' && i.status === 'running' ? { ...i, status: 'done' } : i,
                ),
              )
              setThinkingExpanded(false)
            } else if (item.kind === 'memory') {
              setStreamItems(prev => {
                let fixed = false
                return prev.map(si => {
                  if (fixed || si.kind !== 'thinking') return si
                  const lastRunningIdx = [...si.children].map((c, i) => [c, i] as const).reverse().find(
                    ([c]) => c.kind === 'memory' && c.status === 'running',
                  )?.[1]
                  if (lastRunningIdx === undefined) return si
                  fixed = true
                  return {
                    ...si,
                    children: si.children.map((c, i) =>
                      i === lastRunningIdx ? { ...c, status: 'done' as const } : c,
                    ),
                  }
                })
              })
            } else if (item.kind === 'tool_call') {
              setStreamItems(prev => {
                let fixed = false
                return prev.map(si => {
                  if (fixed || si.kind !== 'thinking') return si
                  const lastRunningIdx = [...si.children].map((c, i) => [c, i] as const).reverse().find(
                    ([c]) => c.kind === 'tool_call' && (c as ToolCallItem).tool === item.tool && c.status === 'running',
                  )?.[1]
                  if (lastRunningIdx === undefined) return si
                  fixed = true
                  return {
                    ...si,
                    children: si.children.map((c, i) =>
                      i === lastRunningIdx ? { ...c, status: 'done' as const } : c,
                    ),
                  }
                })
              })
            }
          }

          if (e.type === 'delta' && e.text) {
            assembled += e.text
            setStreamingText(assembled)
          }
          if (e.type === 'error') {
            streamHadSseErrorRef.current = true
            setSendError(
              typeof e.detail === 'string' && e.detail.trim()
                ? e.detail
                : 'The assistant returned an error.',
            )
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
      setStreamItems([])
      setThinkingExpanded(false)
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
      if (!streamHadSseErrorRef.current) {
        setPendingAttachments([])
        setSendError(null)
      }
    }
  }

  const runStreamRef = React.useRef(runStream)
  runStreamRef.current = runStream

  const pendingStream = location.state?.pendingStream

  const pendingAttachIdsKey = (pendingStream?.attachment_ids ?? []).join(',')

  React.useLayoutEffect(() => {
    if (conversationId == null) return
    const pending = pendingStream
    if (!pending?.bootstrapId) return
    const hasPayload =
      Boolean(pending.content?.trim()) ||
      (pending.attachment_ids != null && pending.attachment_ids.length > 0)
    if (!hasPayload) return
    const key = `aip-bs-${pending.bootstrapId}`
    if (sessionStorage.getItem(key)) return
    sessionStorage.setItem(key, '1')

    const body: Record<string, unknown> = {
      content:
        pending.content.trim() ||
        (pending.attachment_ids?.length ? '(Attached files)' : ''),
      use_rag: pending.use_rag,
    }
    if (pending.model) body.model = pending.model
    if (pending.attachment_ids?.length)
      body.attachment_ids = pending.attachment_ids

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
  }, [
    conversationId,
    navigate,
    pendingAttachIdsKey,
    pendingStream?.bootstrapId,
    pendingStream?.content,
    pendingStream?.model,
    pendingStream?.use_rag,
  ])

  const sendStream = async (text: string) => {
    const trimmed = text.trim()
    const canSend =
      Boolean(trimmed) ||
      (!isComposerMode && pendingAttachments.length > 0) ||
      (isComposerMode && pendingComposerFiles.length > 0)
    if (!canSend) return

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
            knowledge_base_ids: draftKbIds,
          }),
        })
        if (!res.ok) {
          setSendError(await res.text())
          return
        }
        const created = (await res.json()) as { id: number }
        const attachment_ids: number[] = []
        const filesToSend = [...pendingComposerFiles]
        for (const f of filesToSend) {
          const fd = new FormData()
          fd.append('file', f)
          const up = await fetch(
            `${apiBase}/api/chat/conversations/${created.id}/uploads`,
            { method: 'POST', headers: await getAuthHeaders(), body: fd },
          )
          if (!up.ok) {
            setSendError(await up.text())
            return
          }
          attachment_ids.push((await up.json()).id as number)
        }
        setPendingComposerFiles([])
        void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
        const modelParam = draftModel.trim() || undefined
        const bootstrapId = crypto.randomUUID()
        const streamContent =
          trimmed || (attachment_ids.length > 0 ? '(Attached files)' : '')
        setComposeDraft('')
        void navigate({
          to: '/chat/conversations/$id',
          params: { id: String(created.id) },
          replace: true,
          state: {
            pendingStream: {
              bootstrapId,
              content: streamContent,
              use_rag: draftKbIds.length > 0,
              ...(modelParam ? { model: modelParam } : {}),
              ...(attachment_ids.length > 0 ? { attachment_ids } : {}),
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
      content: trimmed || (pendingAttachments.length > 0 ? '(Attached files)' : ''),
      use_rag: true,
    }
    if (modelParam) body.model = modelParam
    if (pendingAttachments.length > 0)
      body.attachment_ids = pendingAttachments.map((a) => a.id)
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
      <header className="hidden shrink-0 items-start justify-between gap-1.5 border-b border-neutral-200 pb-2 dark:border-neutral-800 md:flex">
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
              data-testid="thread-header-delete-open"
              className="rounded border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
              disabled={deleteConv.isPending}
              onClick={() => setConfirmDeleteOpen(true)}
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
              data-testid="chat-load-older"
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
        {!threadMessagesLoading &&
          !showEmptyHub &&
          visibleMessages.length > 0 &&
          chatStartersFetched &&
          chatStarters?.sections &&
          chatStarters.sections.length > 0 && (
            <details
              data-testid="chat-starters-collapsed"
              className="mb-4 rounded-lg border border-neutral-200/80 bg-neutral-50/50 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900/40"
            >
              <summary className="cursor-pointer text-xs font-medium text-neutral-600 dark:text-neutral-400">
                Suggested prompts
              </summary>
              <div className="mt-2 border-t border-neutral-200/60 pt-3 dark:border-neutral-700">
                <StartersPanel
                  variant="sidebar"
                  sections={chatStarters.sections}
                  setComposeDraft={setComposeDraft}
                />
              </div>
            </details>
          )}
        <ul className="flex w-full flex-col gap-5" role="log" aria-label="Conversation messages">
          {visibleMessages.map((m) => {
            const isUserSide = m.role === 'user'
            const isSystem = m.role === 'system'
            const isLatestAssistant =
              m.role === 'assistant' && lastMessageId === m.id && !streaming
            const isErrorAssistant =
              m.role === 'assistant' && isPersistedStreamErrorMessage(m.content)
            const roleLabel =
              isErrorAssistant ? 'error' : m.role === 'system' ? 'system' : m.role
            const userAttachments =
              (m.extra?.attachments as
                | { id: number; original_filename: string }[]
                | undefined) ?? []
            return (
              <li
                key={m.id}
                data-testid={`chat-message-${m.role}`}
                className={`flex w-full text-sm ${isUserSide ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`rounded-2xl px-4 py-3 ${
                    isUserSide
                      ? 'ml-auto max-w-[85%] md:max-w-[70%] bg-neutral-100/95 text-neutral-900 dark:bg-neutral-800/95 dark:text-neutral-100'
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
                      {m.role === 'assistant' && !isErrorAssistant && (
                        <MessageKbIndicator usedKbs={usedKbsFromMessage(m)} />
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
                    {isUserSide && userAttachments.length > 0 && (
                      <ul
                        className="mb-2 flex flex-wrap gap-1.5"
                        aria-label="Attachments sent with this message"
                      >
                        {userAttachments.map((a) => (
                          <li
                            key={a.id}
                            className="rounded-full border border-neutral-200/90 bg-white/80 px-2 py-0.5 text-[10px] text-neutral-700 dark:border-neutral-600 dark:bg-neutral-950/60 dark:text-neutral-300"
                          >
                            {a.original_filename}
                          </li>
                        ))}
                      </ul>
                    )}
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
                </div>
              </li>
            )
          })}
        </ul>
        {!streaming &&
          streamItems.some((i) => i.kind === 'thinking') && (
            <div className="mt-1 w-full">
              <div className="w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75">
                <StreamingThinkingBlock
                  items={streamItems}
                  expanded={thinkingExpanded}
                  onToggle={() => setThinkingExpanded((e) => !e)}
                />
              </div>
            </div>
          )}
        {streaming && (
          <div className="mt-1 w-full">
            <div
              className="stream-surface-breathe w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75"
              aria-live="polite"
              aria-busy="true"
              aria-label="Assistant is responding"
            >
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
              <StreamingThinkingBlock
                items={streamItems}
                expanded={thinkingExpanded}
                onToggle={() => setThinkingExpanded(e => !e)}
              />
              {streamingText ? (
                <MarkdownMessage
                  content={streamingText}
                  streaming
                  className="text-neutral-900 dark:text-neutral-100"
                />
              ) : streamItems.length === 0 ? (
                <p className="flex items-center gap-2 text-sm text-neutral-400">
                  <span className="inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
                  Waiting for tokens…
                </p>
              ) : null}
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
          <p>{sendError}</p>
          {lastStreamBodyRef.current && (
            <button
              type="button"
              data-testid="chat-stream-retry"
              className="mt-2 text-xs font-medium text-blue-700 underline decoration-dotted underline-offset-2 dark:text-blue-400"
              disabled={streaming}
              onClick={() => {
                const b = lastStreamBodyRef.current
                if (b) void runStream(b)
              }}
            >
              Retry
            </button>
          )}
        </div>
      )}

      <div ref={composerRef} className="w-full shrink-0">
        {isMobile ? (
          <ChatComposerDockMobile
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
            capabilityDescriptions={capabilityDescriptions}
            composeDraft={composeDraft}
            setComposeDraft={setComposeDraft}
            onSubmit={() => { if (!streaming) void sendStream(composeDraft) }}
            pendingServerAttachments={isComposerMode ? undefined : pendingAttachments}
            pendingLocalFileNames={isComposerMode ? pendingComposerFiles.map((f) => f.name) : undefined}
            onRemoveServerAttachment={(id) => setPendingAttachments((p) => p.filter((x) => x.id !== id))}
            onRemoveLocalFile={(index) => setPendingComposerFiles((p) => p.filter((_, i) => i !== index))}
            onLocalFilesChosen={onLocalFilesChosen}
            attachDisabled={streaming}
            streaming={streaming}
            onStop={stopStream}
            inputThemed={inputThemed}
            kbSlot={
              isComposerMode ? (
                <KbChatPicker
                  conversationId={null}
                  activeCount={draftKbIds.length}
                  draftKnowledgeBaseIds={draftKbIds}
                  onDraftKnowledgeBaseIdsChange={setDraftKbIds}
                />
              ) : conversationId != null ? (
                <KbChatPicker conversationId={conversationId} activeCount={knowledge_base_ids.length} />
              ) : undefined
            }
            selectedCatalogModel={selectedCatalogModel}
            tuning={sessionTuning}
            onTuningChange={setSessionTuning}
          />
        ) : (
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
            capabilityDescriptions={capabilityDescriptions}
            composeDraft={composeDraft}
            setComposeDraft={setComposeDraft}
            onSubmit={() => { if (!streaming) void sendStream(composeDraft) }}
            pendingServerAttachments={isComposerMode ? undefined : pendingAttachments}
            pendingLocalFileNames={isComposerMode ? pendingComposerFiles.map((f) => f.name) : undefined}
            onRemoveServerAttachment={(id) => setPendingAttachments((p) => p.filter((x) => x.id !== id))}
            onRemoveLocalFile={(index) => setPendingComposerFiles((p) => p.filter((_, i) => i !== index))}
            onLocalFilesChosen={onLocalFilesChosen}
            attachDisabled={streaming}
            streaming={streaming}
            onStop={stopStream}
            inputThemed={inputThemed}
            kbSlot={
              isComposerMode ? (
                <KbChatPicker
                  conversationId={null}
                  activeCount={draftKbIds.length}
                  draftKnowledgeBaseIds={draftKbIds}
                  onDraftKnowledgeBaseIdsChange={setDraftKbIds}
                />
              ) : conversationId != null ? (
                <KbChatPicker conversationId={conversationId} activeCount={knowledge_base_ids.length} />
              ) : undefined
            }
            selectedCatalogModel={selectedCatalogModel}
            tuning={sessionTuning}
            onTuningChange={setSessionTuning}
          />
        )}
      </div>
      {confirmDeleteOpen && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/45 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-thread-title"
          onClick={(e) => e.target === e.currentTarget && setConfirmDeleteOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-xl border border-neutral-200 bg-white p-4 shadow-xl dark:border-neutral-700 dark:bg-neutral-950"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="delete-thread-title" className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
              Delete conversation?
            </h2>
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
              This will permanently delete the conversation and all messages.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
                onClick={() => setConfirmDeleteOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500 disabled:opacity-50"
                disabled={deleteConv.isPending}
                onClick={() => {
                  deleteConv.mutate()
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
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
