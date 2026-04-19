import { useLocation, useNavigate } from '@tanstack/react-router'
import { Copy } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import {
  ChatComposerDock,
  resolveSelectedCatalogModel,
} from '~/components/chat/ChatComposerDock'
import { ChatComposerDockMobile } from '~/components/chat/ChatComposerDockMobile'
import { EmptyConversationState } from '~/components/chat/EmptyConversationState'
import { MarkdownMessage } from '~/components/chat/MarkdownMessage'
import { StartersPanel } from '~/components/chat/StartersPanel'
import { ThreadItemChip } from '~/components/chat/ThreadItemChip'
import { MessageKbIndicator } from '~/components/knowledge-bases/MessageKbIndicator'
import { KbChatPicker } from '~/components/knowledge-bases/KbChatPicker'
import { MessageUsageBadge } from '~/components/chat/MessageUsageBadge'
import { QuotaBanner } from '~/components/chat/QuotaBanner'
import { useConversationsOutlet } from '~/contexts/ConversationsOutletContext'
import { useCatalogModelsQuery } from '~/hooks/useCatalogModelsQuery'
import { useChatCapabilityProfileQuery } from '~/hooks/useChatCapabilityProfileQuery'
import { useIsMobile } from '~/hooks/useIsMobile'
import { useThread } from '~/hooks/useThread'
import { isConversationNotFoundError } from '~/lib/conversation-not-found'
import type { ChatMessage, StreamThreadItem, UsedKbEntry } from '~/lib/chat-types'
import type { SessionModelTuning } from '~/components/chat/ModelTuningModal'
import { defaultTuningFromCatalog } from '~/components/chat/ModelTuningModal'

const randomUUID = (): string =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
      })

/** Distance from scroll bottom (px) treated as "following" the thread. */
const THREAD_BOTTOM_STICKY_PX = 80

function PersistedStreamItems({ message }: { message: ChatMessage }) {
  const items = message.extra?.stream_items as StreamThreadItem[] | undefined
  if (!items?.length) return null
  return (
    <div className="mb-2 flex flex-col gap-1.5">
      {items.map((item, i) => (
        <ThreadItemChip key={item.uid ?? i} item={{ ...item, status: 'done' }} />
      ))}
    </div>
  )
}

function isPersistedStreamErrorMessage(content: string): boolean {
  return content.trimStart().startsWith('**Error:**')
}

function usedKbsFromMessage(m: ChatMessage): UsedKbEntry[] {
  const raw = m.used_kbs ?? m.extra?.used_kbs
  return Array.isArray(raw) ? (raw as UsedKbEntry[]) : []
}

export type ConversationThreadPageProps = {
  conversationId: number | null
}

export function ConversationThreadPage({ conversationId }: ConversationThreadPageProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { composeDraft, setComposeDraft, chatStarters, chatStartersFetched } =
    useConversationsOutlet()
  const { isMobile } = useIsMobile()
  const catalogQ = useCatalogModelsQuery()
  const capProfileQ = useChatCapabilityProfileQuery(true)

  // ── Thread hook ────────────────────────────────────────────────────────────
  const {
    conversation, conversationPending, conversationError,
    patchPending,
    deleteConversation, deletePending,
    thread, threadPending, canLoadOlder, loadingOlder, loadOlder,
    streaming, streamingText, streamThreadItems, sendError, setSendError,
    retryStream, stopStream, lastStreamBodyRef,
    submitMessage, regenerate,
    chatModel, setChatModel, commitChatModel,
    capabilities, setCapabilities: _sc, toggleCapability,
    draftKbIds, setDraftKbIds,
    pendingAttachments, setPendingAttachments,
    pendingComposerFiles, setPendingComposerFiles,
    uploadFile,
  } = useThread(conversationId, {
    onConversationCreated: (id, bootstrap) => {
      const bootstrapId = randomUUID()
      void navigate({
        to: '/chat/conversations/$id',
        params: { id: String(id) },
        replace: true,
        state: { pendingStream: { bootstrapId, ...bootstrap } },
      })
    },
    onDeleteSuccess: () => void navigate({ to: '/chat/conversations' }),
  })

  // ── UI-only state ──────────────────────────────────────────────────────────
  const [confirmDeleteOpen, setConfirmDeleteOpen] = React.useState(false)
  const [sessionTuning, setSessionTuning] = React.useState<SessionModelTuning>(() =>
    defaultTuningFromCatalog(null),
  )

  // Keep session tuning in sync with the resolved catalog model.
  const selectedCatalogModel = resolveSelectedCatalogModel(catalogQ.data, chatModel)
  React.useEffect(() => {
    setSessionTuning(defaultTuningFromCatalog(selectedCatalogModel))
  }, [selectedCatalogModel?.id, chatModel])

  const capabilityDescriptions = React.useMemo(
    () =>
      capProfileQ.data
        ? {
            reflection: capProfileQ.data.reflection.description,
            research: capProfileQ.data.research.description,
          }
        : undefined,
    [capProfileQ.data],
  )

  // ── Scroll management ──────────────────────────────────────────────────────
  const messagesScrollRef = React.useRef<HTMLDivElement>(null)
  const stickToBottomRef = React.useRef(true)
  const programmaticScrollRef = React.useRef(false)
  const wasStreamingRef = React.useRef(false)
  const composerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    stickToBottomRef.current = true
  }, [conversationId])

  const scrollThreadToBottom = React.useCallback((behavior: ScrollBehavior) => {
    const el = messagesScrollRef.current
    if (!el) return
    programmaticScrollRef.current = true
    el.scrollTo({ top: el.scrollHeight, behavior })
    // Clear the flag after the animation settles so user-initiated scrolls
    // are detected again (smooth ~400 ms, instant is synchronous).
    if (behavior === 'instant' || behavior === 'auto') {
      programmaticScrollRef.current = false
    } else {
      setTimeout(() => { programmaticScrollRef.current = false }, 450)
    }
  }, [])

  const syncStickToBottomFromScroll = React.useCallback(() => {
    // Ignore scroll events that we triggered ourselves — intermediate positions
    // during a smooth-scroll animation would otherwise flip stickToBottom off.
    if (programmaticScrollRef.current) return
    const el = messagesScrollRef.current
    if (!el) return
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    stickToBottomRef.current = gap <= THREAD_BOTTOM_STICKY_PX
  }, [])

  // During active streaming: instant scroll on every text delta so we always
  // stay at the bottom without triggering a visible animation on each chunk.
  React.useLayoutEffect(() => {
    if (!streaming) return
    if (!stickToBottomRef.current) return
    scrollThreadToBottom('instant')
  }, [streamingText, streaming, scrollThreadToBottom])

  // When the thread changes (new message landed) or streaming state changes:
  // use a smooth scroll so the transition feels intentional.
  React.useLayoutEffect(() => {
    if (!stickToBottomRef.current) return
    const raf = requestAnimationFrame(() => scrollThreadToBottom('smooth'))
    return () => cancelAnimationFrame(raf)
  }, [thread, scrollThreadToBottom])

  // Extra scroll after stream ends — content height may have grown as the
  // streaming bubble is replaced by the final persisted message.
  React.useEffect(() => {
    const wasStreaming = wasStreamingRef.current
    wasStreamingRef.current = streaming
    if (!wasStreaming || streaming) return
    if (!stickToBottomRef.current) return
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => scrollThreadToBottom('smooth'))
    })
    return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner) }
  }, [streaming, scrollThreadToBottom])

  // ── iOS visual viewport — push composer above keyboard ────────────────────
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

  // ── Navigate away if conversation not found ────────────────────────────────
  const conversationMissing =
    conversationId != null &&
    conversationError != null &&
    isConversationNotFoundError(String((conversationError as Error)?.message ?? ''))

  React.useEffect(() => {
    if (!conversationMissing) return
    void navigate({ to: '/chat/conversations', replace: true })
  }, [conversationMissing, navigate])

  // ── Bootstrap: auto-start stream after navigating to a new conversation ───
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
    void (async () => {
      try {
        await submitMessage(
          pending.content?.trim() || '',
          {
            model: pending.model,
            attachmentIds: pending.attachment_ids,
            use_rag: pending.use_rag,
          },
        )
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
    conversationId, navigate, pendingAttachIdsKey,
    pendingStream?.bootstrapId, pendingStream?.content,
    pendingStream?.model, pendingStream?.use_rag,
    submitMessage,
  ])

  // ── File upload helper used by both composer components ───────────────────
  const onLocalFilesChosen = React.useCallback(
    async (files: File[]) => {
      for (const f of files.slice(0, 5)) await uploadFile(f)
    },
    [uploadFile],
  )

  // ── Guards ────────────────────────────────────────────────────────────────
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
  if (conversationId != null && conversationError) {
    return (
      <p className="text-red-600 text-sm">
        {(conversationError as Error).message || 'Could not load conversation.'}
      </p>
    )
  }

  // ── Derived UI ────────────────────────────────────────────────────────────
  const isComposerMode = conversationId == null
  const knowledge_base_ids = conversation?.knowledge_base_ids ?? []
  const threadMessagesLoading =
    !isComposerMode && !streaming && thread.length === 0 &&
    (conversationPending || threadPending)
  const showEmptyHub =
    !streaming && streamThreadItems.length === 0 && thread.length === 0 &&
    (isComposerMode || (conversation != null && !threadPending))

  const surfaceThemed =
    'border-neutral-200 bg-neutral-50 text-neutral-900 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-100'
  const inputThemed =
    'border-neutral-300 bg-white text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100'

  const displayTitle = isComposerMode
    ? 'New conversation'
    : conversation?.title?.trim() || 'New conversation'

  const lastMessageId = thread.at(-1)?.id

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
      {/* ── Desktop header ─────────────────────────────────────────────────── */}
      <header className="hidden shrink-0 items-start justify-between gap-1.5 border-b border-neutral-200 pb-2 dark:border-neutral-800 md:flex">
        <div className="min-w-0 flex-1 space-y-0.5">
          <h1 className="truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100 sm:text-base">
            {displayTitle}
          </h1>
          {!isComposerMode && conversation?.created_at && (
            <p className="text-xs text-neutral-400">
              Created {formatWhen(conversation.created_at)}
            </p>
          )}
        </div>
        {!isComposerMode && (
          <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
            <button
              type="button"
              data-testid="thread-header-delete-open"
              className="rounded border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
              disabled={deletePending}
              onClick={() => setConfirmDeleteOpen(true)}
            >
              Delete
            </button>
          </div>
        )}
      </header>

      {/* ── Messages scroll area ───────────────────────────────────────────── */}
      <div
        ref={messagesScrollRef}
        onScroll={syncStickToBottomFromScroll}
        className={`min-h-0 w-full min-w-0 flex-1 overflow-y-auto overflow-x-hidden scroll-pb-4 scroll-smooth overscroll-contain rounded-xl border p-4 sm:p-5 ${surfaceThemed}`}
      >
        {canLoadOlder && thread.length > 0 && (
          <div className="mb-3 flex justify-center">
            <button
              type="button"
              data-testid="chat-load-older"
              className="text-xs text-blue-600 underline decoration-dotted disabled:opacity-50"
              disabled={loadingOlder}
              onClick={() => void loadOlder()}
            >
              {loadingOlder ? 'Loading…' : 'Load older messages'}
            </button>
          </div>
        )}

        {threadMessagesLoading ? (
          <div className="flex min-h-[min(50dvh,22rem)] w-full items-center justify-center px-4">
            <PrismLogo state="loading" size={40} />
          </div>
        ) : showEmptyHub ? (
          <EmptyConversationState
            starters={chatStarters}
            startersFetched={chatStartersFetched}
            setComposeDraft={setComposeDraft}
          />
        ) : (
          <>
            {thread.length > 0 && chatStartersFetched && chatStarters?.sections?.length && (
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
              {thread.map((m) => {
                const isUserSide = m.role === 'user'
                const isSystem = m.role === 'system'
                const isLatestAssistant = m.role === 'assistant' && lastMessageId === m.id && !streaming
                const isErrorAssistant = m.role === 'assistant' && isPersistedStreamErrorMessage(m.content)
                const roleLabel = isErrorAssistant ? 'error' : m.role === 'system' ? 'system' : m.role
                const userAttachments =
                  (m.extra?.attachments as { id: number; original_filename: string }[] | undefined) ?? []
                return (
                  <li
                    key={m.id}
                    data-testid={`chat-message-${m.role}`}
                    className={`flex w-full text-sm ${isUserSide ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`rounded-2xl px-4 py-3 ${
                      isUserSide
                        ? 'ml-auto max-w-[85%] md:max-w-[70%] bg-neutral-100/95 text-neutral-900 dark:bg-neutral-800/95 dark:text-neutral-100'
                        : isSystem
                          ? 'w-full max-w-none bg-neutral-100/70 text-neutral-800 dark:bg-neutral-800/50 dark:text-neutral-200'
                          : isErrorAssistant
                            ? 'w-full max-w-none bg-red-50/90 dark:bg-red-950/35'
                            : 'w-full max-w-none bg-white/90 dark:bg-neutral-900/75'
                    }`}>
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span className={`text-[10px] font-semibold uppercase tracking-wide ${
                          isErrorAssistant ? 'text-red-600 dark:text-red-400' : 'text-neutral-500 dark:text-neutral-400'
                        }`}>
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
                              data-testid="chat-regenerate"
                              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 underline decoration-dotted decoration-neutral-400/80 underline-offset-2 hover:text-neutral-900 disabled:opacity-40 dark:text-neutral-400 dark:decoration-neutral-500 dark:hover:text-neutral-200"
                              disabled={streaming}
                              onClick={() => void regenerate(m.id)}
                            >
                              Regenerate
                            </button>
                          )}
                        </div>
                      </div>
                      {userAttachments.length > 0 && (
                        <ul className="mb-1.5 flex flex-wrap gap-1" aria-label="Attachments">
                          {userAttachments.map((a) => (
                            <li key={a.id} className="rounded-full border border-neutral-200/90 bg-white/80 px-2 py-0.5 text-[10px] text-neutral-700 dark:border-neutral-600 dark:bg-neutral-950/60 dark:text-neutral-300">
                              {a.original_filename}
                            </li>
                          ))}
                        </ul>
                      )}
                      {m.role === 'assistant' && <PersistedStreamItems message={m} />}
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
                      {m.role === 'assistant' && !isErrorAssistant && (
                        <MessageUsageBadge extra={m.extra} />
                      )}
                    </div>
                  </li>
                )
              })}

              {sendError && !streaming && (
                <li data-testid="chat-message-assistant" className="flex w-full justify-start text-sm">
                  <div className="w-full max-w-none rounded-2xl bg-red-50/90 px-4 py-3 dark:bg-red-950/35">
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-red-600 dark:text-red-400">error</span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          className="rounded p-1 text-neutral-500 transition-colors hover:bg-neutral-200/70 disabled:opacity-40 dark:text-neutral-400 dark:hover:bg-neutral-700/60"
                          aria-label="Copy message"
                          onClick={() => void copyToClipboard(sendError)}
                        >
                          <Copy className="size-3.5" strokeWidth={2} />
                        </button>
                        {lastStreamBodyRef.current && (
                          <button
                            type="button"
                            data-testid="chat-stream-retry"
                            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 underline decoration-dotted decoration-neutral-400/80 underline-offset-2 hover:text-neutral-900 disabled:opacity-40 dark:text-neutral-400 dark:decoration-neutral-500 dark:hover:text-neutral-200"
                            onClick={() => void retryStream()}
                          >
                            Retry
                          </button>
                        )}
                      </div>
                    </div>
                    <MarkdownMessage content={`**Error:** ${sendError}`} className="text-red-800 dark:text-red-200" />
                  </div>
                </li>
              )}
            </ul>

            {(streaming || streamThreadItems.length > 0) && (
              <div className="mt-1 w-full">
                <div
                  className="stream-surface-breathe w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75"
                  aria-live="polite"
                  aria-busy={streaming}
                  aria-label={streaming ? 'Assistant is responding' : 'Assistant response items'}
                >
                  {streamThreadItems.length > 0 && (
                    <div className="mb-2 flex flex-col gap-1.5">
                      {streamThreadItems.map((item) => (
                        <ThreadItemChip key={item.uid} item={item} />
                      ))}
                    </div>
                  )}
                  {streamingText && (
                    <MarkdownMessage
                      content={streamingText}
                      streaming
                      className="text-neutral-900 dark:text-neutral-100"
                    />
                  )}
                  {streaming && (
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <PrismLogo
                        state={sendError ? 'error' : streamingText || streamThreadItems.length > 0 ? 'streaming' : 'loading'}
                        size={20}
                      />
                      <button
                        type="button"
                        className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 underline decoration-dotted dark:text-red-400"
                        onClick={stopStream}
                      >
                        Stop
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Quota warning ─────────────────────────────────────────────────────── */}
      <QuotaBanner />

      {/* ── Composer ──────────────────────────────────────────────────────────── */}
      <div ref={composerRef} className="w-full shrink-0">
        {isMobile ? (
          <ChatComposerDockMobile
            models={catalogQ.data}
            modelsPending={catalogQ.isPending}
            modelsError={catalogQ.error as Error | null}
            chatModel={chatModel}
            onSelectChatModel={setChatModel}
            onCommitChatModel={isComposerMode ? undefined : commitChatModel}
            modelSelectDisabled={!isComposerMode && patchPending}
            capabilities={capabilities}
            onToggleCapability={toggleCapability}
            capabilityDisabled={!isComposerMode && patchPending}
            capabilityDescriptions={capabilityDescriptions}
            composeDraft={composeDraft}
            setComposeDraft={setComposeDraft}
            onSubmit={() => { if (!streaming) { setComposeDraft(''); void submitMessage(composeDraft) } }}
            pendingServerAttachments={isComposerMode ? undefined : pendingAttachments}
            pendingLocalFileNames={isComposerMode ? pendingComposerFiles.map(f => f.name) : undefined}
            onRemoveServerAttachment={(id) => setPendingAttachments(p => p.filter(x => x.id !== id))}
            onRemoveLocalFile={(i) => setPendingComposerFiles(p => p.filter((_, j) => j !== i))}
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
            chatModel={chatModel}
            onSelectChatModel={setChatModel}
            onCommitChatModel={isComposerMode ? undefined : commitChatModel}
            modelSelectDisabled={!isComposerMode && patchPending}
            capabilities={capabilities}
            onToggleCapability={toggleCapability}
            capabilityDescriptions={capabilityDescriptions}
            composeDraft={composeDraft}
            setComposeDraft={setComposeDraft}
            onSubmit={() => { if (!streaming) { setComposeDraft(''); void submitMessage(composeDraft) } }}
            pendingServerAttachments={isComposerMode ? undefined : pendingAttachments}
            pendingLocalFileNames={isComposerMode ? pendingComposerFiles.map(f => f.name) : undefined}
            onRemoveServerAttachment={(id) => setPendingAttachments(p => p.filter(x => x.id !== id))}
            onRemoveLocalFile={(i) => setPendingComposerFiles(p => p.filter((_, j) => j !== i))}
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

      {/* ── Delete confirmation dialog ─────────────────────────────────────── */}
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
                disabled={deletePending}
                onClick={() => { setConfirmDeleteOpen(false); deleteConversation() }}
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

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatWhen(iso: string) {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch { return iso }
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    window.prompt('Copy:', text)
  }
}
