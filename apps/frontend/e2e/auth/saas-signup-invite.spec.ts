/**
 * SaaS signup + invite — end-to-end through the UI.
 *
 * Covers the SaaS self-serve onboarding loop:
 *   1. A brand-new org owner registers (email/password) → lands authenticated.
 *   2. Owner opens admin → Members → invites a second email.
 *   3. The invite token (delivered by email in prod) is read off the UI's own
 *      create-invitation network response — there is no inbox in E2E.
 *   4. A SECOND browser context (no shared session) opens the invite link and
 *      the invitee registers / accepts → joins the org.
 *
 * All interactions go through the browser UI. The only "API" touch is reading a
 * response the UI itself triggered (allowed — the test never calls the backend
 * directly). This runs with a fresh, UNauthenticated context (storageState
 * cleared) so registration starts from a logged-out state.
 *
 * Against the in-memory mock backend the invite POST returns a `token`; against
 * a real E2E backend the same field is expected on the invitation payload.
 */
import { test, expect } from '../support/fixtures'

// These flows must start logged-out; drop the global storageState.
test.use({ storageState: { cookies: [], origins: [] } })

const REGISTER = async (page: import('@playwright/test').Page, email: string, password: string) => {
  await page.goto('/register', { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('you@company.com').fill(email)
  await page.getByPlaceholder('Min. 8 characters').fill(password)
  await page.getByPlaceholder('••••••••').fill(password)
  await page.getByRole('button', { name: /create account/i }).click()
  // Token stored → app navigates off /register.
  await page.waitForURL((u) => !/\/register/.test(u.pathname), { timeout: 30_000 })
}

test.describe('SaaS signup + invite', () => {
  test('owner registers, invites a teammate, invitee joins the org', async ({ page, browser }) => {
    const stamp = Date.now()
    const ownerEmail = `e2e-owner-${stamp}@vortex.test`
    const inviteeEmail = `e2e-invitee-${stamp}@vortex.test`
    const password = 'E2ePassw0rd!seed'

    // ── 1. Owner registers ────────────────────────────────────────────────
    await REGISTER(page, ownerEmail, password)
    await expect(page).toHaveURL((u) => !/\/register/.test(u.pathname))

    // ── 2. Owner invites a teammate from admin → Members ──────────────────
    await page.goto('/admin/members', { waitUntil: 'domcontentloaded' })
    const inviteForm = page.getByTestId('admin-members-invite-form')
    await expect(inviteForm).toBeVisible({ timeout: 15_000 })

    // Capture the invite token off the UI-triggered create-invitation request.
    const invitePromise = page.waitForResponse(
      (r) =>
        /\/members\/invitations$/.test(new URL(r.url()).pathname) &&
        r.request().method() === 'POST',
      { timeout: 15_000 },
    )

    await inviteForm.getByPlaceholder('colleague@example.com').fill(inviteeEmail)
    await inviteForm.getByRole('button', { name: /invite/i }).click()

    const inviteRes = await invitePromise
    const inviteBody = (await inviteRes.json()) as { token?: string; invite_url?: string }
    const token = inviteBody.token
    expect(token, 'invite response must carry a token to build the accept link').toBeTruthy()

    // Pending invitation shows in the table.
    await expect(
      page.getByTestId('admin-invitations-table').getByText(inviteeEmail),
    ).toBeVisible({ timeout: 15_000 })

    // ── 3. Invitee accepts in a fresh context (no shared session) ─────────
    const inviteeCtx = await browser.newContext()
    const inviteePage = await inviteeCtx.newPage()
    try {
      // The register page accepts an invite via ?invite=<token>. The invitee
      // registers (POST /api/v1/auth/register) then the app calls the
      // authenticated POST /api/v1/auth/invites/:token/accept to join the org.
      await inviteePage.goto(`/register?invite=${token}`, { waitUntil: 'domcontentloaded' })
      await expect(inviteePage.getByText(/accept invite/i)).toBeVisible({ timeout: 15_000 })
      await inviteePage.getByPlaceholder('you@company.com').fill(inviteeEmail)
      await inviteePage.getByPlaceholder('Min. 8 characters').fill(password)
      await inviteePage.getByPlaceholder('••••••••').fill(password)
      await inviteePage.getByRole('button', { name: /accept & sign in/i }).click()

      // Joined → routed into the app (off the auth route) with a stored token.
      await inviteePage.waitForURL((u) => !/\/(register|login|invite)/.test(u.pathname), {
        timeout: 30_000,
      })
      const stored = await inviteePage.evaluate(() => localStorage.getItem('aip_access_token'))
      expect(stored, 'invitee should hold a session token after accepting').toBeTruthy()
    } finally {
      await inviteeCtx.close()
    }
  })
})
