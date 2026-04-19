/**
 * Admin Policies tab — verify RBAC controls render and save button is present.
 */
import { test, expect } from '@playwright/test'

const RBAC_ROUTE = '**/api/admin/rbac/policy'
const MODELS_ROUTE = '**/api/models'

test.describe('Admin — Policies tab', () => {
  test('Policies tab renders capability and tool tables', async ({ page }) => {
    await page.route(MODELS_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { slug: 'claude-sonnet', display_name: 'Claude Sonnet', accessible: true, can_request_access: false, request_access_url: null },
          { slug: 'gpt-4o', display_name: 'GPT-4o', accessible: true, can_request_access: false, request_access_url: null },
        ]),
      })
    })

    await page.route(RBAC_ROUTE, async (route) => {
      if (route.request().method() === 'PUT') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, org_id: 'test', model_allowlist: null, model_role_bindings: {}, capability_role_bindings: {}, tool_role_bindings: {}, default_policy: 'allow', updated_at: '2026-04-15T10:00:00Z' }) })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          org_id: 'test-org',
          model_allowlist: null,
          model_role_bindings: {},
          capability_role_bindings: {},
          tool_role_bindings: {},
          default_policy: 'allow',
          updated_at: '2026-04-15T10:00:00Z',
        }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Policies' }).click()

    // Capability table headers.
    await expect(page.getByText('Capabilities — required roles')).toBeVisible()
    await expect(page.getByText('Tools — required roles')).toBeVisible()

    // Model allowlist section.
    await expect(page.getByText('Model allowlist')).toBeVisible()

    // Save button.
    await expect(page.getByRole('button', { name: /Save/i })).toBeVisible()
  })

  test('Default policy radio buttons are present', async ({ page }) => {
    await page.route(MODELS_ROUTE, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })
    await page.route(RBAC_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, org_id: 'x', model_allowlist: null, model_role_bindings: {}, capability_role_bindings: {}, tool_role_bindings: {}, default_policy: 'allow', updated_at: '2026-04-15T10:00:00Z' }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Policies' }).click()

    await expect(page.getByLabel(/allow all/i)).toBeVisible()
    await expect(page.getByLabel(/deny all/i)).toBeVisible()
  })
})
