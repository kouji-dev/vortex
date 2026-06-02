import { test, expect } from '../support/fixtures'

test.describe('Worker spawn — repo picker', () => {
  test('connect-first guard when no repos', async ({ page }) => {
    await page.route('**/v1/workers/git-integrations**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    )

    await page.goto('/workers/instances', { waitUntil: 'domcontentloaded' })
    await page.getByTestId('wk-instance-spawn-open').click()

    const drawer = page.getByTestId('wk-instance-spawn-drawer')
    await expect(drawer).toBeVisible()

    // No-repo callout should be visible
    await expect(page.getByTestId('wk-instance-spawn-no-repo')).toBeVisible()

    // Connect link should be present and point to integrations page
    const connectLink = page.getByTestId('wk-instance-spawn-connect-link')
    await expect(connectLink).toBeVisible()
    await expect(connectLink).toHaveAttribute('href', /\/workers\/integrations/)

    // Spawn submit button should be disabled when no repos are connected
    const submitBtn = page.getByTestId('wk-instance-spawn-submit')
    await expect(submitBtn).toBeDisabled()
  })

  test('repo picker shows enabled repos', async ({ page }) => {
    const mockIntegrations = [
      {
        id: 'i1',
        kind: 'github',
        account_login: 'octocat',
        scope: 'user',
        auth_type: 'token',
        enabled: true,
        repos: [
          {
            id: 'r1',
            full_name: 'octocat/web',
            default_branch: 'main',
            enabled: true,
          },
        ],
      },
    ]

    await page.route('**/v1/workers/git-integrations**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockIntegrations),
      }),
    )

    await page.goto('/workers/instances', { waitUntil: 'domcontentloaded' })
    await page.getByTestId('wk-instance-spawn-open').click()

    const drawer = page.getByTestId('wk-instance-spawn-drawer')
    await expect(drawer).toBeVisible()

    // Repo select should be visible
    const repoSelect = page.getByTestId('wk-instance-spawn-repo')
    await expect(repoSelect).toBeVisible()

    // Should contain option with the repo full_name
    await expect(repoSelect.locator('option', { hasText: 'octocat/web' })).toBeAttached()

    // No-repo callout should NOT be present
    await expect(page.getByTestId('wk-instance-spawn-no-repo')).toHaveCount(0)
  })
})
