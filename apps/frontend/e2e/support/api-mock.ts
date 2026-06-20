/**
 * Stateful in-browser mock of the backend API — lets frontend E2E run with NO
 * backend / DB / Docker. A single `**­/api/**` dispatcher serves every call the
 * app makes; conversations are kept in an in-memory store so CRUD stays
 * consistent (create → list → open → send).
 *
 * Phase 1 covers the app-shell + chat. Unknown endpoints return an empty
 * default so page loads never break. Per-test mocks (e.g. `installChatStreamMock`)
 * registered AFTER this win, because Playwright tries the most-recently-added
 * route first.
 *
 * Shapes mirror the typed hooks (`me-types.ts`, `chat-types.ts`) so they stay
 * honest against the real backend.
 */
import type { Page, Route } from '@playwright/test'

import { buildStreamBody, makeItem, newTurnId } from './chat-mock'

const ORG_ID = '00000000-0000-0000-0000-000000000001'

const MOCK_USER = {
  id: 1,
  email: 'dev@localhost',
  roles: ['owner'],
  display_name: 'Dev User',
  given_name: 'Dev',
  family_name: 'User',
  preferred_username: 'dev@localhost',
}

function model(
  id: number,
  slug: string,
  displayName: string,
  apiModelId: string,
  provider: string,
  isDefault = false,
): Record<string, unknown> {
  return {
    id,
    slug,
    display_name: displayName,
    description: null,
    api_model_id: apiModelId,
    provider,
    accessible: true,
    is_default: isDefault,
    sort_order: id,
    effort: 'medium',
    model_settings: {
      reasoning: { supported: false, efforts_available: [] },
      features: { vision: false, tool_use: true },
      sampling: {
        temperature: { min: 0, max: 2, default: 1 },
        max_output_tokens: { min: 1, max: 8192, default: 4096 },
      },
    },
    can_request_access: false,
    request_access_url: null,
  }
}

const MOCK_MODELS = [
  model(1, 'google-gemini-2-5-flash-lite', 'Gemini 2.5 Flash Lite', 'gemini-2.5-flash-lite', 'google', true),
  model(2, 'anthropic-claude-haiku-4-5', 'Claude Haiku 4.5', 'claude-haiku-4-5', 'anthropic'),
  model(3, 'openai-o3-mini', 'o3-mini', 'o3-mini', 'openai'),
]

interface MockConversation {
  id: number
  org_id: string
  user_id: number
  assistant_id: number | null
  title: string | null
  model: string | null
  settings: Record<string, unknown> | null
  summary: string | null
  last_message_at: string | null
  created_at: string
  knowledge_base_ids: number[]
}

export interface MockApi {
  conversations: MockConversation[]
  messages: Map<number, Record<string, unknown>[]>
}

/** Install the stateful API mock on a page. Call once per test (via the fixture). */
export async function installApiMock(page: Page): Promise<MockApi> {
  const conversations: MockConversation[] = []
  const messages = new Map<number, Record<string, unknown>[]>()
  let nextId = 1

  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  const bodyOf = (route: Route): Record<string, unknown> => {
    try {
      return (route.request().postDataJSON() as Record<string, unknown>) ?? {}
    } catch {
      return {}
    }
  }

  // Health badge polls /health (proxied to the backend, which doesn't exist).
  // Serve it so the badge reads "Healthy" and `networkidle` can settle.
  await page.route('**/health', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  )

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const method = req.method()

    // ── Realtime SSE: complete instantly so `networkidle` settles ────────────
    if (path === '/api/events') {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: ready\ndata: {}\n\n',
      })
    }

    // ── App-shell reads ──────────────────────────────────────────────────────
    if (path === '/api/me') return json(route, MOCK_USER)
    if (path === '/api/models') return json(route, MOCK_MODELS)
    if (path === '/api/chat/starters') return json(route, { sections: [] })
    if (path === '/api/chat/capability-profile') {
      return json(route, {
        reflection: { description: 'Think step by step before answering.' },
        research: { description: 'Search and cross-reference sources.' },
      })
    }
    if (path === '/api/admin/usage/my') {
      return json(route, { limited: false, used: 0, limit: null, remaining: null })
    }

    // ── Conversations collection ─────────────────────────────────────────────
    if (path === '/api/chat/conversations') {
      if (method === 'GET') return json(route, conversations)
      if (method === 'POST') {
        const body = bodyOf(route)
        const conv: MockConversation = {
          id: nextId++,
          org_id: ORG_ID,
          user_id: 1,
          assistant_id: (body.assistant_id as number) ?? null,
          title: (body.title as string) ?? null,
          model: (body.model as string) ?? (MOCK_MODELS[0].api_model_id as string),
          settings: (body.settings as Record<string, unknown>) ?? { capabilities: {} },
          summary: null,
          last_message_at: null,
          created_at: new Date().toISOString(),
          knowledge_base_ids: (body.knowledge_base_ids as number[]) ?? [],
        }
        conversations.unshift(conv)
        messages.set(conv.id, [])
        return json(route, conv, 201)
      }
    }

    // ── Single conversation: GET / PATCH / DELETE ────────────────────────────
    let m = path.match(/^\/api\/chat\/conversations\/(\d+)$/)
    if (m) {
      const id = Number(m[1])
      const conv = conversations.find((c) => c.id === id)
      if (method === 'GET') return conv ? json(route, conv) : json(route, { detail: 'not found' }, 404)
      if (method === 'PATCH') {
        if (conv) Object.assign(conv, bodyOf(route))
        return json(route, conv ?? {})
      }
      if (method === 'DELETE') {
        const i = conversations.findIndex((c) => c.id === id)
        if (i >= 0) conversations.splice(i, 1)
        messages.delete(id)
        return route.fulfill({ status: 204, body: '' })
      }
    }

    // ── Messages tail (GET) ──────────────────────────────────────────────────
    m = path.match(/^\/api\/chat\/conversations\/(\d+)\/messages$/)
    if (m && method === 'GET') return json(route, messages.get(Number(m[1])) ?? [])

    // ── Stream a turn (POST): persist user + assistant, return canned SSE ─────
    m = path.match(/^\/api\/chat\/conversations\/(\d+)\/messages\/stream$/)
    if (m && method === 'POST') {
      const id = Number(m[1])
      const body = bodyOf(route)
      const userText = (body.content as string) ?? ''
      const turnId = newTurnId()
      const arr = messages.get(id) ?? []
      const base = 800 + arr.length
      arr.push(
        makeItem('user_message', { text: userText, attachments: [] }, { id: base, threadId: id, turnId, role: 'user' }),
        makeItem('assistant_text', { text: 'OK' }, { id: base + 1, threadId: id, turnId }),
      )
      messages.set(id, arr)
      const conv = conversations.find((c) => c.id === id)
      if (conv) conv.last_message_at = new Date().toISOString()
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: buildStreamBody({ threadId: id, turnId, userText, assistantText: 'OK' }),
      })
    }

    // ── Uploads (POST) ───────────────────────────────────────────────────────
    m = path.match(/^\/api\/chat\/conversations\/(\d+)\/uploads$/)
    if (m && method === 'POST') return json(route, { id: 1, filename: 'upload', size: 0 }, 201)

    // ── Unknown endpoint: empty default so page loads don't break ────────────
    if (method === 'GET') return json(route, [])
    return json(route, {})
  })

  return { conversations, messages }
}
