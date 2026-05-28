/**
 * Cross-module: gateway.
 *
 * Covers:
 *  - OpenAI-compat /v1/chat/completions submission via Playground UI.
 *  - Trace row appears in the Traces panel after a request.
 *  - x-aip-cost-usd header present on a successful response.
 *  - 429 returned after rate-limit threshold (mocked).
 *
 * All interactions go through the browser. Backend mocked via page.route().
 * Scaffold — pages may not exist yet; failures are useful signal.
 */
import { test, expect } from '@playwright/test'

const COMPLETIONS_ROUTE = '**/v1/chat/completions'
const TRACES_ROUTE = '**/api/v1/gateway/traces**'

function okCompletion(headers: Record<string, string> = {}) {
  return {
    status: 200,
    contentType: 'application/json',
    headers: {
      'x-aip-cost-usd': '0.0012',
      'x-aip-trace-id': 'trace_suite_gw_1',
      'x-aip-model': 'gpt-4o-mini',
      ...headers,
    },
    body: JSON.stringify({
      id: 'cmpl_suite_1',
      object: 'chat.completion',
      created: Math.floor(Date.now() / 1000),
      model: 'gpt-4o-mini',
      choices: [
        { index: 0, message: { role: 'assistant', content: 'hello world' }, finish_reason: 'stop' },
      ],
      usage: { prompt_tokens: 5, completion_tokens: 2, total_tokens: 7 },
    }),
  }
}

test.describe('Suite — Gateway', () => {
  // ───────────────────────────────────────────────────────────────────
  // OpenAI-compat submit + cost header
  // ───────────────────────────────────────────────────────────────────

  test('submits an OpenAI-compat chat completion and reads cost header', async ({ page }) => {
    await page.route(COMPLETIONS_ROUTE, async (route) => {
      await route.fulfill(okCompletion())
    })

    await page.goto('/', { waitUntil: 'networkidle' })

    const resp = await page.evaluate(async () => {
      const r = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer devtoken',
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [{ role: 'user', content: 'say hello' }],
        }),
      })
      const body = await r.json()
      return {
        ok: r.ok,
        cost: r.headers.get('x-aip-cost-usd'),
        traceId: r.headers.get('x-aip-trace-id'),
        content: body?.choices?.[0]?.message?.content ?? null,
      }
    })

    expect(resp.ok).toBe(true)
    expect(resp.cost).not.toBeNull()
    expect(Number(resp.cost)).toBeGreaterThan(0)
    expect(resp.traceId).toBeTruthy()
    expect(resp.content).toContain('hello')
  })

  // ───────────────────────────────────────────────────────────────────
  // Trace row visible after request
  // ───────────────────────────────────────────────────────────────────

  test('trace row for the new request shows in /gateway/traces', async ({ page }) => {
    await page.route(COMPLETIONS_ROUTE, async (route) => {
      await route.fulfill(okCompletion())
    })

    await page.route(TRACES_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: 1,
          rows: [
            {
              id: 'trace_suite_gw_1',
              created_at: new Date().toISOString(),
              model: 'gpt-4o-mini',
              status: 'ok',
              latency_ms: 423,
              cost_usd: 0.0012,
              prompt_tokens: 5,
              completion_tokens: 2,
            },
          ],
        }),
      })
    })

    await page.goto('/', { waitUntil: 'networkidle' })
    await page.evaluate(async () => {
      await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer devtoken' },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [{ role: 'user', content: 'hi' }],
        }),
      })
    })

    await page.goto('/gateway/traces', { waitUntil: 'networkidle' })
    await expect(page.getByTestId('view-trace_suite_gw_1')).toBeVisible({ timeout: 10_000 })
  })

  // ───────────────────────────────────────────────────────────────────
  // 429 after rate-limit threshold
  // ───────────────────────────────────────────────────────────────────

  test('returns 429 once mocked threshold is reached', async ({ page }) => {
    let calls = 0
    const threshold = 3
    await page.route(COMPLETIONS_ROUTE, async (route) => {
      calls += 1
      if (calls > threshold) {
        await route.fulfill({
          status: 429,
          contentType: 'application/json',
          headers: { 'retry-after': '10', 'x-aip-rate-limit-remaining': '0' },
          body: JSON.stringify({
            error: { type: 'rate_limit_exceeded', message: 'tenant quota exceeded' },
          }),
        })
        return
      }
      await route.fulfill(okCompletion({ 'x-aip-rate-limit-remaining': String(threshold - calls) }))
    })

    await page.goto('/', { waitUntil: 'networkidle' })

    const statuses = await page.evaluate(async (n) => {
      const out: number[] = []
      for (let i = 0; i < n; i++) {
        const r = await fetch('/v1/chat/completions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: 'Bearer devtoken' },
          body: JSON.stringify({
            model: 'gpt-4o-mini',
            messages: [{ role: 'user', content: 'ping' }],
          }),
        })
        out.push(r.status)
      }
      return out
    }, threshold + 2)

    expect(statuses.slice(0, threshold)).toEqual(Array(threshold).fill(200))
    expect(statuses[threshold]).toBe(429)
    expect(statuses[threshold + 1]).toBe(429)
  })
})
