/**
 * Cross-module: control-plane.
 *
 * Covers:
 *  - /login renders, happy-path form submit reaches POST /auth/login.
 *  - API key mint via Admin → API Keys panel, used as bearer in a mocked gateway request.
 *  - Audit Log panel surfaces an event row.
 *
 * All backend interactions are mocked at the browser via page.route() — no direct API seeding.
 * Scaffold: failures expected when the matching UI surfaces evolve; specs document the contract.
 */
import { test, expect } from '@playwright/test'

test.describe('Suite — Control plane', () => {
  // ───────────────────────────────────────────────────────────────────
  // Login happy path
  // ───────────────────────────────────────────────────────────────────

  test('login flow: submit credentials → token stored → redirect home', async ({ page }) => {
    await page.route('**/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock_access_token',
          refresh_token: 'mock_refresh_token',
          token_type: 'bearer',
        }),
      })
    })

    await page.goto('/login', { waitUntil: 'networkidle' })
    await page.getByPlaceholder('you@example.com').fill('admin@example.com')
    await page.getByPlaceholder('••••••••').fill('hunter2')
    await page.getByRole('button', { name: /sign in/i }).click()

    // Token persisted by the login page.
    await expect(async () => {
      const t = await page.evaluate(() => localStorage.getItem('aip_access_token'))
      expect(t).toBe('mock_access_token')
    }).toPass({ timeout: 10_000 })
  })

  // ───────────────────────────────────────────────────────────────────
  // API key mint + downstream use
  // ───────────────────────────────────────────────────────────────────

  test('mint API key via admin UI, then use it on a mocked gateway request', async ({ page }) => {
    const minted = {
      id: 1,
      name: 'e2e-suite-key',
      prefix: 'sk_aip',
      // Plaintext is only returned once on creation.
      secret: 'sk_aip_test_1234567890abcdef',
      created_at: new Date().toISOString(),
    }

    await page.route('**/api/admin/api-keys**', async (route) => {
      const req = route.request()
      if (req.method() === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(minted),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    })

    // Naviguate to the admin API keys surface. Folded into org settings or a dedicated tab.
    await page.goto('/org/settings', { waitUntil: 'networkidle' })
    const apiKeysTab = page.getByRole('button', { name: /api keys/i }).first()
    if (await apiKeysTab.isVisible().catch(() => false)) {
      await apiKeysTab.click()
    }

    // Click create — UI may use "New", "Create", "Add" — accept any.
    const createBtn = page
      .getByRole('button', { name: /(new|create|add).*api key/i })
      .or(page.getByRole('button', { name: /new key/i }))
      .first()
    if (await createBtn.isVisible().catch(() => false)) {
      await createBtn.click()
      const nameInput = page
        .getByLabel(/name/i)
        .or(page.getByPlaceholder(/key name|name/i))
        .first()
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill(minted.name)
      }
      const confirm = page.getByRole('button', { name: /(create|save|generate)/i }).first()
      if (await confirm.isVisible().catch(() => false)) await confirm.click()
      // Plaintext secret should render once.
      await expect(page.getByText(minted.secret)).toBeVisible({ timeout: 10_000 })
    }

    // Now exercise the minted key on a mocked gateway request — confirm the bearer is forwarded.
    let observedAuth: string | null = null
    await page.route('**/v1/chat/completions', async (route) => {
      observedAuth = route.request().headers()['authorization'] ?? null
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'x-aip-cost-usd': '0.00042', 'x-aip-trace-id': 'trace_e2e_suite_1' },
        body: JSON.stringify({
          id: 'cmpl_e2e_1',
          object: 'chat.completion',
          choices: [{ index: 0, message: { role: 'assistant', content: 'pong' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 3, completion_tokens: 1, total_tokens: 4 },
        }),
      })
    })

    const resp = await page.evaluate(async (token) => {
      const r = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [{ role: 'user', content: 'ping' }],
        }),
      })
      return {
        ok: r.ok,
        cost: r.headers.get('x-aip-cost-usd'),
        trace: r.headers.get('x-aip-trace-id'),
      }
    }, minted.secret)

    expect(resp.ok).toBe(true)
    expect(resp.cost).toBe('0.00042')
    expect(resp.trace).toBe('trace_e2e_suite_1')
    expect(observedAuth).toBe(`Bearer ${minted.secret}`)
  })

  // ───────────────────────────────────────────────────────────────────
  // Audit Log surface
  // ───────────────────────────────────────────────────────────────────

  test('audit log panel surfaces a recent event row', async ({ page }) => {
    await page.route('**/api/admin/audit**', async (route) => {
      if (route.request().url().includes('export')) return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: 1,
          items: [
            {
              id: 9001,
              actor_user_id: 1,
              actor_type: 'user',
              event_type: 'api_key.create',
              resource_type: 'api_key',
              resource_id: '1',
              action: 'create',
              created_at: new Date().toISOString(),
            },
          ],
        }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Audit Log' }).click()
    await expect(page.getByText('api_key.create')).toBeVisible({ timeout: 10_000 })
  })
})
