/**
 * Browser-level chat-stream mocks for E2E.
 *
 * All chat/agent turns in E2E are mocked at the browser via `page.route()` — no
 * real backend LLM is ever called. This module is the single source of truth for
 * the SSE/item shapes (kept in sync with `apps/frontend/src/lib/chat-types.ts`).
 *
 * Use `installChatStreamMock(page, { script, delayMs })` to mock a send/receive
 * cycle. The default script returns a single `assistant_text` item. Pass `script`
 * to add thinking / tool_call items, usage, or custom assistant text. Pass
 * `delayMs` to keep the stream pending (for Stop-button tests).
 */
import type { Page, Route } from '@playwright/test'

export const STREAM_ROUTE = '**/api/chat/conversations/*/messages/stream'
export const MESSAGES_ROUTE = '**/api/chat/conversations/*/messages*'

/** Default thread id used by mocked turns when the caller does not supply one. */
export const MOCK_THREAD_ID = 9999

// ── Item shapes (mirror ThreadItem in src/lib/chat-types.ts) ────────────────

export type MockItemKind =
  | 'user_message'
  | 'assistant_text'
  | 'thinking'
  | 'tool_call'
  | 'llm_call'
  | 'kb_search'
  | 'citation'
  | 'memory_pill'

export interface MockItemOpts {
  id?: number
  threadId?: number
  turnId?: string
  role?: 'user' | 'assistant' | 'system'
  status?: 'streaming' | 'done' | 'error' | 'cancelled'
  provider?: string | null
  model?: string | null
  latencyMs?: number | null
}

/** Build a single ThreadItem-shaped object with all required base fields. */
export function makeItem(
  kind: MockItemKind,
  data: Record<string, unknown>,
  opts: MockItemOpts = {},
): Record<string, unknown> {
  return {
    id: opts.id ?? 1,
    thread_id: opts.threadId ?? MOCK_THREAD_ID,
    turn_id: opts.turnId ?? newTurnId(),
    kind,
    role: opts.role ?? (kind === 'user_message' ? 'user' : 'assistant'),
    status: opts.status ?? 'done',
    provider: opts.provider ?? null,
    model: opts.model ?? null,
    cost_usd: null,
    cost_estimated: false,
    latency_ms: opts.latencyMs ?? null,
    data,
    parent_item_id: null,
    started_at: null,
    finished_at: null,
    created_at: new Date().toISOString(),
  }
}

/** Generate a unique, valid-looking turn id. */
export function newTurnId(): string {
  return `00000000-0000-4000-8000-${String(Date.now()).slice(-12)}`
}

// ── Script → SSE / GET-messages bodies ──────────────────────────────────────

export interface ChatScript {
  /** Echoed back as the user_message in the GET-messages turn list. */
  userText?: string
  /** Assistant reply text. Defaults to 'OK'. Set to null to omit the assistant_text item. */
  assistantText?: string | null
  /** Optional thinking text — emitted as a `thinking` item before the assistant text. */
  thinking?: string
  /** Optional tool_call items emitted before the assistant text. */
  toolCalls?: {
    tool_name: string
    params?: Record<string, unknown>
    result_snippet?: string
    provider?: string
  }[]
  /** Optional usage (llm_call) item appended to the stream. */
  usage?: {
    input_tokens?: number
    output_tokens?: number
    cached_input_tokens?: number
    cache_creation_input_tokens?: number
    reasoning_tokens?: number
    iteration_index?: number
  }
  /** Override the full turn list returned by GET-messages. When omitted, it is derived. */
  turnItems?: Record<string, unknown>[]
  /** Shared turn/thread ids for all items in this script. */
  turnId?: string
  threadId?: number
}

const sse = (payload: unknown) => `data: ${JSON.stringify(payload)}\n\n`

/** Build the ordered list of stream items (excluding the user message) from a script. */
function buildStreamItems(script: ChatScript): Record<string, unknown>[] {
  const turnId = script.turnId ?? newTurnId()
  const threadId = script.threadId ?? MOCK_THREAD_ID
  const base = { turnId, threadId }
  const items: Record<string, unknown>[] = []
  let id = 900

  if (script.thinking !== undefined) {
    items.push(makeItem('thinking', { text: script.thinking }, { ...base, id: id++ }))
  }
  for (const tc of script.toolCalls ?? []) {
    items.push(
      makeItem(
        'tool_call',
        {
          tool_name: tc.tool_name,
          params: tc.params ?? {},
          result_snippet: tc.result_snippet ?? null,
        },
        { ...base, id: id++, provider: tc.provider ?? null },
      ),
    )
  }
  const assistantText = script.assistantText === undefined ? 'OK' : script.assistantText
  if (assistantText !== null) {
    items.push(makeItem('assistant_text', { text: assistantText }, { ...base, id: id++ }))
  }
  if (script.usage) {
    items.push(
      makeItem(
        'llm_call',
        {
          input_tokens: script.usage.input_tokens ?? 0,
          output_tokens: script.usage.output_tokens ?? 0,
          cached_input_tokens: script.usage.cached_input_tokens ?? 0,
          cache_creation_input_tokens: script.usage.cache_creation_input_tokens ?? 0,
          reasoning_tokens: script.usage.reasoning_tokens ?? 0,
          iteration_index: script.usage.iteration_index ?? 0,
        },
        { ...base, id: id++ },
      ),
    )
  }
  return items
}

/** SSE body string for a script: each item wrapped in `event_type: item`, then `done`. */
export function buildStreamBody(script: ChatScript = {}): string {
  const turnId = script.turnId ?? newTurnId()
  const threadId = script.threadId ?? MOCK_THREAD_ID
  // The real backend emits the persisted user_message as the FIRST SSE frame;
  // useStream drops its optimistic id=-1 user item and, on success, keeps only
  // the streamed items. If the stream omits the user_message, the user bubble
  // vanishes when the stream ends. So emit it first (real id, not -1).
  const userItem = makeItem(
    'user_message',
    { text: script.userText ?? '', attachments: [] },
    { id: 850, turnId, threadId, role: 'user' },
  )
  const items = buildStreamItems({ ...script, turnId, threadId })
  return (
    sse({ event_type: 'item', item: userItem }) +
    items.map((item) => sse({ event_type: 'item', item })).join('') +
    sse({ event_type: 'done' })
  )
}

/** GET-messages turn list (user_message + stream items), or the script override. */
export function buildMessagesBody(script: ChatScript = {}): string {
  if (script.turnItems) return JSON.stringify(script.turnItems)
  const turnId = script.turnId ?? newTurnId()
  const threadId = script.threadId ?? MOCK_THREAD_ID
  const userItem = makeItem(
    'user_message',
    { text: script.userText ?? '', attachments: [] },
    { id: 800, turnId, threadId, role: 'user' },
  )
  // Re-derive stream items with the SAME turn id so the GET list is coherent.
  const streamItems = buildStreamItems({ ...script, turnId, threadId })
  return JSON.stringify([userItem, ...streamItems])
}

// ── Installer ───────────────────────────────────────────────────────────────

export interface InstallChatStreamMockOpts {
  /** Script describing the assistant turn. Defaults to a single 'OK' assistant_text. */
  script?: ChatScript
  /**
   * Keep the stream pending for this many ms before fulfilling (for Stop-button
   * tests). When set, the stream stays open so the composer shows the Stop button.
   */
  delayMs?: number
  /** Restrict routes to a single conversation id (defaults to all conversations). */
  conversationId?: number | string
}

/**
 * Route `**­/messages/stream` (SSE) and `GET **­/messages*` (turn list) for a
 * mocked send/receive cycle. No real LLM is called.
 *
 * Returns an async cleanup fn that unroutes both routes.
 */
export async function installChatStreamMock(
  page: Page,
  opts: InstallChatStreamMockOpts = {},
): Promise<() => Promise<void>> {
  const script = opts.script ?? {}
  // Pin a single turn id so the stream + GET list agree.
  const turnId = script.turnId ?? newTurnId()
  const pinned: ChatScript = { ...script, turnId }

  const cid = opts.conversationId
  const streamRoute =
    cid === undefined ? STREAM_ROUTE : `**/api/chat/conversations/${cid}/messages/stream`
  const messagesRoute =
    cid === undefined ? MESSAGES_ROUTE : `**/api/chat/conversations/${cid}/messages*`

  const streamBody = buildStreamBody(pinned)
  const messagesBody = buildMessagesBody(pinned)

  const streamHandler = async (route: Route) => {
    if (opts.delayMs && opts.delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, opts.delayMs))
    }
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: streamBody })
  }
  const messagesHandler = async (route: Route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: messagesBody })
    } else {
      await route.continue()
    }
  }

  await page.route(streamRoute, streamHandler)
  await page.route(messagesRoute, messagesHandler)

  // Unroute only THIS install's handlers so a fixture-level catch-all survives.
  return async () => {
    await page.unroute(streamRoute, streamHandler).catch(() => undefined)
    await page.unroute(messagesRoute, messagesHandler).catch(() => undefined)
  }
}
