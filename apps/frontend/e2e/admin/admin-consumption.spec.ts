import { test, expect } from '../support/fixtures'

test.describe('Admin consumption page', () => {
  test('consumption nav link is visible in sidebar', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('nav-consumption')).toBeVisible()
  })

  test('consumption page loads with heading', async ({ page }) => {
    await page.goto('/org/consumption', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('consumption-page')).toBeVisible()
    await expect(page.getByRole('heading', { name: /consumption/i })).toBeVisible()
  })

  test('consumption page shows KPI strip section', async ({ page }) => {
    // Mock the summary API to avoid needing a real admin user
    await page.route('**/api/admin/consumption/summary*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          kpis: [
            { label: 'Month Spend', value: 1.23, unit: 'USD', delta_pct: null, is_estimate: false },
            { label: 'Messages', value: 42, unit: '', delta_pct: null, is_estimate: false },
          ],
          by_model: [],
          by_user: [],
          by_provider: [],
          by_capability: [],
          by_tool: [],
        }),
      })
    })
    await page.route('**/api/admin/consumption/trend*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ points: [], grain: 'day', by: 'kind' }),
      })
    })
    await page.route('**/api/admin/consumption/threads*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ rows: [], total: 0, page: 1, page_size: 20 }),
      })
    })

    await page.goto('/org/consumption', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('consumption-page')).toBeVisible()
    // KPI strip should render the mocked data
    await expect(page.locator('.kpi-row')).toBeVisible({ timeout: 5_000 })
  })
})
