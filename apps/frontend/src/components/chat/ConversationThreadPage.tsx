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
import { TurnGroup } from '~/components/chat/items/TurnGroup'
import { KbChatPicker } from '~/components/knowledge-bases/KbChatPicker'
import { QuotaBanner } from '~/components/chat/QuotaBanner'
import { useConversationsOutlet } from '~/contexts/ConversationsOutletContext'
import { useCatalogModelsQuery } from '~/hooks/useCatalogModelsQuery'
import { useChatCapabilityProfileQuery } from '~/hooks/useChatCapabilityProfileQuery'
import { useIsMobile } from '~/hooks/useIsMobile'
import { useMeQuery } from '~/hooks/useMeQuery'
import { useThread } from '~/hooks/useThread'
import { isConversationNotFoundError } from '~/lib/conversation-not-found'
import type { ThreadItem } from '~/lib/chat-types'
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

/** Group thread items by turn_id, preserving insertion order. */
function groupByTurn(items: ThreadItem[]): Map<string, ThreadItem[]> {
  const groups = new Map<string, ThreadItem[]>()
  for (const item of items) {
    const existing = groups.get(item.turn_id) ?? []
    existing.push(item)
    groups.set(item.turn_id, existing)
  }
  return groups
}

export type ConversationThreadPageProps = {
  conversationId: number | null
}

export function ConversationThreadPage({ conversationId }: ConversationThreadPageProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { composeDraft, setComposeDraft, chatStarters, chatStartersFetched, inspectorOpen, setInspectorOpen, setActiveMessage } =
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
    streaming, streamingText, streamItems, sendError, setSendError,
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

  // Silence unused warning — setSendError is kept for consumer APIs.
  void setSendError

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

  // ── Current user (for avatar initials in user messages) ───────────────────
  const me = useMeQuery()
  const userDisplayName = me.data?.display_name ?? me.data?.email ?? 'You'
  const userInitials = React.useMemo(() => {
    const n = me.data?.display_name?.trim()
    if (n) {
      const parts = n.split(/\s+/).filter(Boolean)
      if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      return n.slice(0, 2).toUpperCase()
    }
    if (me.data?.email) return me.data.email.slice(0, 2).toUpperCase()
    return 'U'
  }, [me.data?.display_name, me.data?.email])

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
    // sessionStorage guard deduplicates — submitMessage in deps causes re-runs on model sync
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

  // Group persisted + live items by turn_id.
  const turnGroups = React.useMemo(() => groupByTurn(thread), [thread])
  const turnIds = Array.from(turnGroups.keys())
  const lastPersistedTurnId = turnIds.at(-1)

  const liveGroups = React.useMemo(
    () => (streamItems.length > 0 ? groupByTurn(streamItems) : null),
    [streamItems],
  )
  const liveTurnIds = liveGroups ? Array.from(liveGroups.keys()) : []

  const threadMessagesLoading =
    !isComposerMode && !streaming && thread.length === 0 &&
    (conversationPending || threadPending)
  const showEmptyHub =
    !streaming && streamItems.length === 0 && thread.length === 0 &&
    (isComposerMode || (conversation != null && !threadPending))

  const displayTitle = isComposerMode
    ? 'New conversation'
    : conversation?.title?.trim() || 'New conversation'

  const composerProps = {
    models: catalogQ.data,
    modelsPending: catalogQ.isPending,
    modelsError: catalogQ.error as Error | null,
    chatModel,
    onSelectChatModel: setChatModel,
    onCommitChatModel: isComposerMode ? undefined : commitChatModel,
    modelSelectDisabled: !isComposerMode && patchPending,
    capabilities,
    onToggleCapability: toggleCapability,
    capabilityDescriptions,
    composeDraft,
    setComposeDraft,
    onSubmit: () => { if (!streaming) { setComposeDraft(''); void submitMessage(composeDraft) } },
    pendingServerAttachments: isComposerMode ? undefined : pendingAttachments,
    pendingLocalFileNames: isComposerMode ? pendingComposerFiles.map(f => f.name) : undefined,
    onRemoveServerAttachment: (id: number) => setPendingAttachments(p => p.filter(x => x.id !== id)),
    onRemoveLocalFile: (i: number) => setPendingComposerFiles(p => p.filter((_, j) => j !== i)),
    onLocalFilesChosen,
    attachDisabled: streaming,
    streaming,
    onStop: stopStream,
    inputThemed: 'border-neutral-300 bg-white text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100',
    kbSlot: isComposerMode ? (
      <KbChatPicker
        conversationId={null}
        activeCount={draftKbIds.length}
        draftKnowledgeBaseIds={draftKbIds}
        onDraftKnowledgeBaseIdsChange={setDraftKbIds}
      />
    ) : conversationId != null ? (
      <KbChatPicker conversationId={conversationId} activeCount={knowledge_base_ids.length} />
    ) : undefined,
    selectedCatalogModel,
    tuning: sessionTuning,
    onTuningChange: setSessionTuning,
  }

  return (
    <div className="chat-main">
      {/* ── Chat header ───────────────────────────────────────────────────── */}
      <div className="chat-head">
        <div className="chat-head-title">
          <h2>{displayTitle}</h2>
          <div className="chat-head-meta">
            {!isComposerMode && conversation?.created_at && (
              <>
                <span>Created {formatWhen(conversation.created_at)}</span>
                <span className="sep">·</span>
              </>
            )}
            <span>{turnIds.length} turns</span>
          </div>
        </div>
        <div className="chat-head-actions">
          {!isComposerMode && (
            <button
              type="button"
              data-testid="thread-header-delete-open"
              className="btn btn-sm"
              style={{ color: '#ef4444' }}
              disabled={deletePending}
              onClick={() => setConfirmDeleteOpen(true)}
            >
              Delete
            </button>
          )}
          <button
            type="button"
            className={`btn btn-sm ${inspectorOpen ? 'active' : ''}`}
            data-testid="toggle-inspector"
            onClick={() => setInspectorOpen((v) => !v)}
          >
            Inspect
          </button>
        </div>
      </div>

      {/* ── Messages scroll area ───────────────────────────────────────────── */}
      <div
        ref={messagesScrollRef}
        onScroll={syncStickToBottomFromScroll}
        className="thread-scroll"
        data-testid="chat-thread"
      >
        {canLoadOlder && thread.length > 0 && (
          <div className="mb-3 flex justify-center">
            <button
              type="button"
              data-testid="chat-load-older"
              className="btn btn-sm"
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

            <ul role="log" aria-label="Conversation messages" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {turnIds.map((turnId) => (
                <TurnGroup
                  key={turnId}
                  turnId={turnId}
                  items={turnGroups.get(turnId)!}
                  isLastTurn={turnId === lastPersistedTurnId && !streaming}
                  onSetActive={setActiveMessage}
                  userInitials={userInitials}
                  userDisplayName={userDisplayName}
                  onRegenerate={(tid) => void regenerate(tid)}
                  regenerateDisabled={streaming}
                />
              ))}

              {streaming && liveTurnIds.map((turnId) => (
                <TurnGroup
                  key={`live-${turnId}`}
                  turnId={turnId}
                  items={liveGroups!.get(turnId)!}
                  isStreaming
                  onSetActive={() => {}}
                  userInitials={userInitials}
                  userDisplayName={userDisplayName}
                />
              ))}

              {streaming && streamItems.length === 0 && (
                <li className="msg msg-asst" data-testid="chat-message-assistant">
                  <header className="msg-head">
                    <span className="avatar-sm avatar-asst mono">VX</span>
                    <span className="who-name">Assistant</span>
                  </header>
                  <div className="msg-body">
                    <PrismLogo state="loading" size={20} />
                  </div>
                </li>
              )}

              {sendError && !streaming && (
                <li data-testid="chat-message-assistant" className="msg msg-asst">
                  <header className="msg-head">
                    <span className="avatar-sm avatar-asst mono">VX</span>
                    <span className="who-name" style={{ color: '#ef4444' }}>Error</span>
                  </header>
                  <div className="msg-body md text-red-800 dark:text-red-200">
                    <MarkdownMessage content={`**Error:** ${sendError}`} />
                  </div>
                  <div className="msg-actions">
                    <button
                      type="button"
                      className="btn btn-sm"
                      aria-label="Copy message"
                      onClick={() => void copyToClipboard(sendError)}
                    >
                      <Copy className="size-3.5" strokeWidth={2} />
                    </button>
                    {/* lastStreamBodyRef doesn't trigger re-renders; conditional is safe because sendError gates the render */}
                    {lastStreamBodyRef.current && (
                      <button
                        type="button"
                        data-testid="chat-stream-retry"
                        className="btn btn-sm"
                        onClick={() => void retryStream()}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </li>
              )}
            </ul>
          </>
        )}
      </div>

      {/* ── Quota warning ─────────────────────────────────────────────────────── */}
      <QuotaBanner />

      {/* ── Composer ──────────────────────────────────────────────────────────── */}
      <div ref={composerRef} className="run-compose">
        {isMobile ? (
          <ChatComposerDockMobile {...composerProps} />
        ) : (
          <ChatComposerDock {...composerProps} />
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
