/**
 * Browser-level RAG mocks for E2E.
 *
 * Mocks KB document upload/listing and the streaming answer endpoint at the
 * browser via `page.route()` — no real ingestion, embeddings, or LLM.
 */
import type { Page, Route } from '@playwright/test'

export interface RagDoc {
  id: number
  name: string
  status?: string
  chunks?: number
}

export interface InstallRagMockOpts {
  kbId: number | string
  /** Document id returned on upload + listed once "ready". Defaults to 91234. */
  docId?: number
  /** Document filename. Defaults to 'sample.txt'. */
  docName?: string
  /** Streamed answer tokens. Defaults to a sample answer with a citation. */
  answerTokens?: string[]
  /** Citation appended after the answer tokens. Set to null to omit. */
  citation?: { index?: number; document_id: number; name: string; score?: number } | null
}

/**
 * Route the KB documents endpoint (POST upload + GET listing) and the streaming
 * answer endpoint for a KB. Returns an async cleanup fn.
 */
export async function installRagMock(
  page: Page,
  opts: InstallRagMockOpts,
): Promise<() => Promise<void>> {
  const { kbId } = opts
  const docId = opts.docId ?? 91234
  const docName = opts.docName ?? 'sample.txt'
  const tokens = opts.answerTokens ?? ['Sample ', 'answer ', 'with citation']
  const citation =
    opts.citation === undefined
      ? { index: 1, document_id: docId, name: docName, score: 0.92 }
      : opts.citation

  const docsRoute = `**/api/kbs/${kbId}/documents**`
  const answerRoute = `**/api/kbs/${kbId}/answer**`

  let docReady = false

  await page.route(docsRoute, async (route: Route) => {
    const req = route.request()
    if (req.method() === 'POST') {
      docReady = true
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: docId,
          kb_id: kbId,
          name: docName,
          status: 'ready',
          chunks: 3,
          created_at: new Date().toISOString(),
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: docReady
          ? [
              {
                id: docId,
                kb_id: kbId,
                name: docName,
                status: 'ready',
                chunks: 3,
                created_at: new Date().toISOString(),
              },
            ]
          : [],
        total: docReady ? 1 : 0,
      }),
    })
  })

  await page.route(answerRoute, async (route: Route) => {
    const parts = tokens.map((text) => `data: ${JSON.stringify({ type: 'token', text })}\n\n`)
    if (citation) {
      parts.push(
        `data: ${JSON.stringify({
          type: 'citation',
          index: citation.index ?? 1,
          source: {
            document_id: citation.document_id,
            name: citation.name,
            score: citation.score ?? 0.92,
          },
        })}\n\n`,
      )
    }
    parts.push(`data: ${JSON.stringify({ type: 'done' })}\n\n`)
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: parts.join('') })
  })

  return async () => {
    await page.unroute(docsRoute).catch(() => undefined)
    await page.unroute(answerRoute).catch(() => undefined)
  }
}
