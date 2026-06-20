/**
 * In-memory mock of the AI Portal backend for frontend E2E — NO real backend /
 * DB / Docker. Runs as a tiny node HTTP server that BOTH the SSR render and the
 * browser hit (via the Vite proxy / absolute apiBase), so server + client render
 * identical data and SSR hydration matches.
 *
 * Started by playwright.config `webServer`. State is in-memory and per-process
 * (fresh each suite run), mirroring how the shared E2E DB behaved within a run.
 *
 * Phase 1: app-shell + chat. Unknown endpoints return an empty default so page
 * loads never break. Per-test stream customisation is layered on top at the
 * browser via `installChatStreamMock` (page.route wins for browser fetches).
 */
import { createServer } from 'node:http'

const PORT = Number(process.env.MOCK_PORT ?? 8001)
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

function model(id, slug, displayName, apiModelId, provider, isDefault = false) {
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

const conversations = []
const messages = new Map()
let nextId = 1

// Knowledge-base stores
const kbs = []
const kbDocs = new Map()
const kbConnectors = new Map()
let nextKbId = 1
let nextDocId = 1

// User-memory store
const memos = []
let nextMemoId = 1

// Org members + invitations store (stateful for the saas-signup-invite spec).
const members = []
const invitations = []
let nextInviteId = 1

const now = () => new Date().toISOString()
const newTurnId = () => `00000000-0000-4000-8000-${String(Date.now()).slice(-12)}`

function makeItem(kind, data, { id, threadId, turnId, role }) {
  return {
    id,
    thread_id: threadId,
    turn_id: turnId,
    kind,
    role: role ?? (kind === 'user_message' ? 'user' : 'assistant'),
    status: 'done',
    provider: null,
    model: null,
    cost_usd: null,
    cost_estimated: false,
    latency_ms: null,
    data,
    parent_item_id: null,
    started_at: null,
    finished_at: null,
    created_at: now(),
  }
}

const ev = (o) => `data: ${JSON.stringify(o)}\n\n`
function streamBody(threadId, turnId, userText, assistantText) {
  const u = makeItem('user_message', { text: userText, attachments: [] }, { id: 850, threadId, turnId, role: 'user' })
  const a = makeItem('assistant_text', { text: assistantText }, { id: 851, threadId, turnId })
  return ev({ event_type: 'item', item: u }) + ev({ event_type: 'item', item: a }) + ev({ event_type: 'done' })
}

const send = (res, status, type, body) => {
  res.writeHead(status, { 'Content-Type': type })
  res.end(body)
}
const json = (res, body, status = 200) => send(res, status, 'application/json', JSON.stringify(body))

const server = createServer(async (req, res) => {
  const path = new URL(req.url, 'http://x').pathname
  const method = req.method

  let raw = ''
  for await (const c of req) raw += c
  let body = {}
  if (raw && (req.headers['content-type'] ?? '').includes('json')) {
    try {
      body = JSON.parse(raw)
    } catch {
      body = {}
    }
  }

  // ── Auth (UI-driven E2E seeding) ───────────────────────────────────────────
  // The mock is NOT a real auth server: it does not verify passwords or sign
  // real JWTs. It exists so the register/login UI flow in global-setup (and the
  // saas-signup-invite spec) completes end-to-end and the app stores a token in
  // localStorage (key `aip_access_token`), which gates every protected route.
  const mockTokens = (email) => ({
    access_token: `e2e-mock-access.${Buffer.from(email).toString('base64url')}`,
    refresh_token: `e2e-mock-refresh.${Buffer.from(email).toString('base64url')}`,
    token_type: 'bearer',
  })
  // Public auth-config bootstrap the login page fetches.
  if (path === '/api/v1/auth/config' && method === 'GET') {
    return json(res, { password: true, social: [], directory: false, enterprise: false })
  }
  // Password register (no /api prefix — matches register.tsx) and its proxied twin.
  if ((path === '/auth/register' || path === '/api/v1/auth/register') && method === 'POST') {
    return json(res, mockTokens(body.email ?? 'e2e@vortex.test'), 201)
  }
  // Password login.
  if ((path === '/auth/login' || path === '/api/v1/auth/login') && method === 'POST') {
    return json(res, mockTokens(body.email ?? 'e2e@vortex.test'), 200)
  }
  // Org members list.
  if (path === '/api/v1/members' && method === 'GET') {
    return json(res, members)
  }
  // Invitations list + create (admin/members InviteForm).
  if (path === '/api/v1/members/invitations') {
    if (method === 'GET') return json(res, invitations)
    if (method === 'POST') {
      const token = `inv-${nextInviteId}-${Date.now()}`
      const inv = {
        id: String(nextInviteId++),
        email: body.email ?? '',
        role: body.role ?? 'member',
        invited_by: 'e2e-admin@vortex.test',
        created_at: now(),
        expires_at: new Date(Date.now() + 7 * 864e5).toISOString(),
        // Extra fields the UI table ignores but the spec reads off the network
        // response to build the /invite/<token> link (no email inbox in E2E).
        token,
        invite_url: `/invite/${token}`,
      }
      invitations.unshift(inv)
      return json(res, inv, 201)
    }
  }
  // Revoke invitation.
  {
    const rv = path.match(/^\/api\/v1\/members\/invitations\/([^/]+)$/)
    if (rv && method === 'DELETE') {
      const i = invitations.findIndex((x) => x.id === rv[1])
      if (i >= 0) invitations.splice(i, 1)
      return send(res, 204, 'text/plain', '')
    }
  }
  // Accept invite when already authenticated (invite.$token.tsx path).
  {
    const im = path.match(/^\/api\/v1\/auth\/invites\/([^/]+)\/accept$/)
    if (im && method === 'POST') {
      const token = im[1]
      const inv = invitations.find((x) => x.token === token)
      if (inv) {
        members.unshift({
          user_id: `u-${inv.id}`,
          email: inv.email,
          name: null,
          role: inv.role,
          joined_at: now(),
          last_active_at: now(),
        })
        const i = invitations.indexOf(inv)
        if (i >= 0) invitations.splice(i, 1)
      }
      return json(res, { ok: true, org_id: ORG_ID }, 200)
    }
  }

  // ── App-shell + static reads ───────────────────────────────────────────────
  if (path === '/health') return json(res, { status: 'ok' })
  if (path === '/api/events') return send(res, 200, 'text/event-stream', 'event: ready\ndata: {}\n\n')
  if (path === '/api/me') return json(res, MOCK_USER)
  if (path === '/api/models') {
    const wantWorker = new URL(req.url, 'http://x').searchParams.get('usable_in_worker') === 'true'
    const tagged = MOCK_MODELS.map((m) => ({
      ...m,
      usable_in_worker: m.api_model_id.startsWith('claude-') || m.api_model_id.includes('codex'),
    }))
    return json(res, wantWorker ? tagged.filter((m) => m.usable_in_worker) : tagged)
  }
  if (path === '/api/chat/starters') return json(res, { sections: [] })
  if (path === '/api/chat/capability-profile') {
    return json(res, {
      reflection: { description: 'Think step by step before answering.' },
      research: { description: 'Search and cross-reference sources.' },
    })
  }
  if (path === '/api/admin/usage/my') {
    return json(res, { limited: false, used: 0, limit: null, remaining: null })
  }

  // ── Conversations collection ───────────────────────────────────────────────
  if (path === '/api/chat/conversations') {
    if (method === 'GET') return json(res, conversations)
    if (method === 'POST') {
      const conv = {
        id: nextId++,
        org_id: ORG_ID,
        user_id: 1,
        assistant_id: body.assistant_id ?? null,
        title: body.title ?? null,
        model: body.model ?? MOCK_MODELS[0].api_model_id,
        settings: body.settings ?? { capabilities: {} },
        summary: null,
        last_message_at: null,
        created_at: now(),
        knowledge_base_ids: body.knowledge_base_ids ?? [],
      }
      conversations.unshift(conv)
      messages.set(conv.id, [])
      return json(res, conv, 201)
    }
  }

  // ── Single conversation ────────────────────────────────────────────────────
  let m = path.match(/^\/api\/chat\/conversations\/(\d+)$/)
  if (m) {
    const id = Number(m[1])
    const conv = conversations.find((c) => c.id === id)
    if (method === 'GET') return conv ? json(res, conv) : json(res, { detail: 'not found' }, 404)
    if (method === 'PATCH') {
      if (conv) Object.assign(conv, body)
      return json(res, conv ?? {})
    }
    if (method === 'DELETE') {
      const i = conversations.findIndex((c) => c.id === id)
      if (i >= 0) conversations.splice(i, 1)
      messages.delete(id)
      return send(res, 204, 'text/plain', '')
    }
  }

  // ── Conversation ↔ knowledge-base attachment (PUT replaces the set) ──────────
  m = path.match(/^\/api\/chat\/conversations\/(\d+)\/knowledge-bases$/)
  if (m) {
    const id = Number(m[1])
    const conv = conversations.find((c) => c.id === id)
    if (method === 'PUT' || method === 'POST') {
      if (conv) conv.knowledge_base_ids = body.knowledge_base_ids ?? []
      return json(res, conv ?? {})
    }
    if (method === 'GET') return json(res, conv?.knowledge_base_ids ?? [])
  }

  // ── Messages tail ──────────────────────────────────────────────────────────
  m = path.match(/^\/api\/chat\/conversations\/(\d+)\/messages$/)
  if (m && method === 'GET') return json(res, messages.get(Number(m[1])) ?? [])

  // ── Stream a turn ──────────────────────────────────────────────────────────
  m = path.match(/^\/api\/chat\/conversations\/(\d+)\/messages\/stream$/)
  if (m && method === 'POST') {
    const id = Number(m[1])
    const userText = body.content ?? ''
    const turnId = newTurnId()
    const arr = messages.get(id) ?? []
    const base = 800 + arr.length
    arr.push(
      makeItem('user_message', { text: userText, attachments: [] }, { id: base, threadId: id, turnId, role: 'user' }),
      makeItem('assistant_text', { text: 'OK' }, { id: base + 1, threadId: id, turnId }),
    )
    messages.set(id, arr)
    const conv = conversations.find((c) => c.id === id)
    if (conv) conv.last_message_at = now()
    return send(res, 200, 'text/event-stream', streamBody(id, turnId, userText, 'OK'))
  }

  // ── Uploads ────────────────────────────────────────────────────────────────
  m = path.match(/^\/api\/chat\/conversations\/(\d+)\/uploads$/)
  if (m && method === 'POST') {
    const fn = (raw.match(/filename="([^"]+)"/) || [])[1] ?? 'upload.txt'
    const size = Math.max(1, Buffer.byteLength(raw))
    return json(
      res,
      { id: nextDocId++, original_filename: fn, filename: fn, size_bytes: size, size, status: 'ready' },
      201,
    )
  }

  // ── Knowledge bases (stateful CRUD + documents) ──────────────────────────────
  const kbSummary = (kb) => {
    const docs = kbDocs.get(kb.id) ?? []
    return { ...kb, document_count: docs.length, chunks_count: docs.length, size_bytes: 0 }
  }

  if (path === '/api/knowledge-bases/page' && method === 'GET') {
    return json(res, { items: kbs.map(kbSummary), next_cursor: null })
  }
  if (path === '/api/knowledge-bases/providers-config' && method === 'GET') {
    return json(res, { embedders: [], vector_stores: [], chunkers: [] })
  }
  if (path === '/api/knowledge-bases') {
    if (method === 'GET') return json(res, kbs.map(kbSummary))
    if (method === 'POST') {
      const kb = {
        id: nextKbId++,
        name: body.name ?? 'Untitled',
        description: body.description ?? '',
        owner_user_id: 1,
        created_at: now(),
        tags: [],
      }
      kbs.unshift(kb)
      kbDocs.set(kb.id, [])
      kbConnectors.set(kb.id, [])
      return json(res, kbSummary(kb), 201)
    }
  }
  let k = path.match(/^\/api\/knowledge-bases\/(\d+)\/connectors$/)
  if (k) {
    const id = Number(k[1])
    if (method === 'GET') return json(res, kbConnectors.get(id) ?? [])
    if (method === 'POST') {
      const c = {
        id: nextDocId++,
        knowledge_base_id: id,
        kind: body.kind ?? 'files',
        label: body.label ?? 'Files',
        settings: body.settings ?? {},
        enabled: true,
        created_at: now(),
      }
      const arr = kbConnectors.get(id) ?? []
      arr.push(c)
      kbConnectors.set(id, arr)
      return json(res, c, 201)
    }
  }
  k = path.match(/^\/api\/knowledge-bases\/(\d+)\/connector-jobs$/)
  if (k && method === 'GET') return json(res, [])
  k = path.match(/^\/api\/knowledge-bases\/(\d+)\/documents\/(\d+)\/progress$/)
  if (k && method === 'GET') {
    return json(res, { status: 'ready', chunks_total: 1, chunks_done: 1 })
  }
  k = path.match(/^\/api\/knowledge-bases\/(\d+)\/documents\/(\d+)$/)
  if (k) {
    const id = Number(k[1])
    const docId = Number(k[2])
    if (method === 'DELETE') {
      kbDocs.set(id, (kbDocs.get(id) ?? []).filter((d) => d.id !== docId))
      return send(res, 204, 'text/plain', '')
    }
    if (method === 'GET') {
      const d = (kbDocs.get(id) ?? []).find((x) => x.id === docId)
      return d ? json(res, d) : json(res, { detail: 'not found' }, 404)
    }
  }
  k = path.match(/^\/api\/knowledge-bases\/(\d+)\/documents$/)
  if (k) {
    const id = Number(k[1])
    if (method === 'GET') return json(res, kbDocs.get(id) ?? [])
    if (method === 'POST') {
      const fn = (raw.match(/filename="([^"]+)"/) || [])[1] ?? `doc-${nextDocId}.txt`
      const doc = { id: nextDocId++, knowledge_base_id: id, filename: fn, status: 'ready', created_at: now() }
      const arr = kbDocs.get(id) ?? []
      arr.push(doc)
      kbDocs.set(id, arr)
      return json(res, { results: [{ id: doc.id, filename: fn, status: 'ready' }] }, 201)
    }
  }
  k = path.match(/^\/api\/knowledge-bases\/(\d+)$/)
  if (k) {
    const id = Number(k[1])
    const kb = kbs.find((x) => x.id === id)
    if (method === 'GET') {
      return kb ? json(res, kbSummary(kb)) : json(res, { detail: 'Knowledge base not found' }, 404)
    }
    if (method === 'PATCH') {
      if (kb) Object.assign(kb, body)
      return json(res, kb ? kbSummary(kb) : {})
    }
    if (method === 'DELETE') {
      const i = kbs.findIndex((x) => x.id === id)
      if (i >= 0) kbs.splice(i, 1)
      kbDocs.delete(id)
      return send(res, 204, 'text/plain', '')
    }
  }

  // ── Admin consumption (valid empty shapes so the page doesn't crash) ─────────
  if (path === '/api/admin/consumption/summary' && method === 'GET') {
    return json(res, {
      kpis: [],
      by_model: [],
      by_user: [],
      by_provider: [],
      by_capability: [],
      by_tool: [],
    })
  }
  if (path === '/api/admin/consumption/trend' && method === 'GET') {
    return json(res, { points: [], grain: 'day', by: 'kind' })
  }
  if (path === '/api/admin/consumption/threads' && method === 'GET') {
    return json(res, { rows: [], total: 0, page: 1, page_size: 20 })
  }

  // ── User memories (stateful) ─────────────────────────────────────────────
  if (path === '/api/users/me/memories/page' && method === 'GET') {
    return json(res, { items: memos, next_cursor: null })
  }
  if (path === '/api/users/me/memories' || path === '/api/users/me/memories/') {
    if (method === 'GET') return json(res, memos)
    if (method === 'POST') {
      const mem = {
        id: nextMemoId++,
        content: body.content ?? '',
        is_system: false,
        is_active: true,
        source: 'manual',
        created_at: now(),
      }
      memos.unshift(mem)
      return json(res, mem, 201)
    }
  }
  const mm = path.match(/^\/api\/users\/me\/memories\/(\d+)$/)
  if (mm) {
    const id = Number(mm[1])
    const mem = memos.find((x) => x.id === id)
    if (method === 'DELETE') {
      const i = memos.findIndex((x) => x.id === id)
      if (i >= 0) memos.splice(i, 1)
      return send(res, 204, 'text/plain', '')
    }
    if (method === 'PATCH') {
      if (mem) Object.assign(mem, body)
      return json(res, mem ?? {})
    }
    if (method === 'GET') return mem ? json(res, mem) : json(res, { detail: 'not found' }, 404)
  }

  // ── Unknown endpoint: empty default so page loads don't break ─────────────
  if (method === 'GET') return json(res, [])
  return json(res, {})
})

server.listen(PORT, '127.0.0.1', () => {
  // eslint-disable-next-line no-console
  console.log(`[mock-server] AI Portal mock listening on http://127.0.0.1:${PORT}`)
})
