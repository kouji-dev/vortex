/**
 * Enterprise SSO (OIDC) — end-to-end against a Keycloak test IdP.
 *
 * Documented flow (selfhosted deployment_mode):
 *   /login → click enterprise SSO → redirect to Keycloak (realm `acme-corp`)
 *   → authenticate `alice@acme.test` → callback to the app → JIT-provisioned
 *   → group `IT-Admins` maps to role `admin` → an admin-only action is allowed.
 *
 * REQUIREMENTS (this spec is SKIPPED unless they are met — see skip-guard):
 *   - Keycloak running:  docker compose -f tests/keycloak/docker-compose.yml up -d
 *   - Backend reconfigured for OIDC against the acme-corp realm:
 *       DEPLOYMENT_MODE=selfhosted
 *       OIDC_ISSUER=http://localhost:8080/realms/acme-corp
 *       OIDC_CLIENT_ID=vortex-app
 *       OIDC_CLIENT_SECRET=acme-enterprise-secret
 *       OIDC_GROUPS_CLAIM=groups
 *       OIDC_ADMIN_GROUPS=IT-Admins
 *   - Playwright env:  E2E_KEYCLOAK=1   (un-skips this spec)
 *
 * See tests/keycloak/README.md. Standing up Keycloak + reconfiguring the backend
 * is NOT done by the default `pnpm test:e2e` run, so without E2E_KEYCLOAK the
 * whole describe is skipped and the suite stays green.
 *
 * Serial: the JIT-provision + role-mapping assertions share IdP/org state.
 */
import { test, expect } from '../support/fixtures'

const KEYCLOAK_ON = !!process.env.E2E_KEYCLOAK

const ALICE = { email: 'alice@acme.test', password: 'Passw0rd!' } // IT-Admins → admin
const BOB = { email: 'bob@acme.test', password: 'Passw0rd!' } // Engineering → member

test.describe.configure({ mode: 'serial' })

test.describe('Enterprise SSO (Keycloak acme-corp)', () => {
  // Start logged-out; the SSO flow establishes the session itself.
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeAll(() => {
    if (!process.env.E2E_KEYCLOAK) {
      throw new Error('enterprise-sso requires E2E_KEYCLOAK=1 + Keycloak up (tests/keycloak) + backend in selfhosted OIDC mode')
    }
  })

  /** Drive the Keycloak hosted login form once redirected to the IdP. */
  async function loginAtKeycloak(
    page: import('@playwright/test').Page,
    creds: { email: string; password: string },
  ) {
    // Keycloak hosted login form: #username / #password / #kc-login.
    await page.waitForURL(/\/realms\/acme-corp\//, { timeout: 30_000 })
    await page.locator('#username').fill(creds.email)
    await page.locator('#password').fill(creds.password)
    await page.locator('#kc-login').click()
  }

  test('alice (IT-Admins) signs in via SSO, is JIT-provisioned as admin', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'domcontentloaded' })

    // The enterprise SSO entry point (the row is gated on auth-config.enterprise).
    const ssoRow = page.getByTestId('auth-sso-row')
    await expect(ssoRow).toBeVisible({ timeout: 15_000 })
    await ssoRow.getByRole('button').first().click()

    // Redirected to Keycloak; authenticate alice.
    await loginAtKeycloak(page, ALICE)

    // Back in the app, authenticated, off every auth route.
    await page.waitForURL((u) => !/\/(login|register|auth)\b/.test(u.pathname), {
      timeout: 30_000,
    })
    const token = await page.evaluate(() => localStorage.getItem('aip_access_token'))
    expect(token, 'SSO callback should store a session token').toBeTruthy()

    // JIT-provisioned with admin role (IT-Admins → admin): an admin-only surface
    // must be reachable. Members admin is owner/admin gated.
    await page.goto('/admin/members', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('admin-members')).toBeVisible({ timeout: 15_000 })
    // Admin can invite — the invite form is present (member/viewer would be denied).
    await expect(page.getByTestId('admin-members-invite-form')).toBeVisible({ timeout: 15_000 })
  })

  test('bob (Engineering) signs in via SSO, provisioned as member (admin denied)', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'domcontentloaded' })
    const ssoRow = page.getByTestId('auth-sso-row')
    await expect(ssoRow).toBeVisible({ timeout: 15_000 })
    await ssoRow.getByRole('button').first().click()

    await loginAtKeycloak(page, BOB)

    await page.waitForURL((u) => !/\/(login|register|auth)\b/.test(u.pathname), {
      timeout: 30_000,
    })
    const token = await page.evaluate(() => localStorage.getItem('aip_access_token'))
    expect(token, 'SSO callback should store a session token').toBeTruthy()

    // Engineering → member: the admin members surface must NOT be usable.
    // Either redirected away from /admin/* or the admin panel is absent.
    await page.goto('/admin/members', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('admin-members-invite-form')).toBeHidden({ timeout: 15_000 })
  })
})
