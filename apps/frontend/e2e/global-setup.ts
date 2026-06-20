/**
 * Global setup — UI-driven auth seeding (replaces the removed dev-bearer mode).
 *
 * Dev auth is gone: the app is now a real OIDC-consumer / token-bearer that
 * gates every protected route on a JWT in localStorage (`aip_access_token`).
 * So the suite must arrive *authenticated*. We do that the compliant way —
 * through the real browser UI, once — then persist the session via Playwright
 * `storageState`, which `playwright.config.ts` loads into every test's context.
 *
 * Flow (against the E2E frontend the webServer started):
 *   1. Open /register, create a shared E2E user.
 *   2. If that user already exists, fall back to /login.
 *   3. Wait until the app navigates off the auth route (token now stored).
 *   4. Save storageState to e2e/.auth/state.json.
 *
 * No backend API calls here — only the browser. Works against both the
 * in-memory mock-server (default `pnpm test:e2e`) and a real E2E backend
 * (port 8001), since both honour the register/login UI flow.
 */
import { chromium, type FullConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
export const STORAGE_STATE = path.join(__dirname, '.auth', 'state.json')

export const E2E_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'e2e-admin@vortex.test',
  password: process.env.E2E_USER_PASSWORD ?? 'E2ePassw0rd!seed',
}

export default async function globalSetup(config: FullConfig) {
  const baseURL =
    config.projects[0]?.use?.baseURL ??
    process.env.E2E_BASE_URL ??
    'http://localhost:5175'

  const browser = await chromium.launch()
  const context = await browser.newContext({ baseURL })
  const page = await context.newPage()

  const waitForAuthed = async () => {
    // App stores the token then navigates off /register|/login. The auth-redirect
    // guard only lets us stay on a protected route when a token exists.
    await page.waitForURL((url) => !/\/(register|login)(\/|$|\?)/.test(url.pathname), {
      timeout: 30_000,
    })
    await page.waitForFunction(() => !!localStorage.getItem('aip_access_token'), null, {
      timeout: 30_000,
    })
  }

  // 1. Try register.
  await page.goto('/register', { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('you@company.com').fill(E2E_USER.email)
  await page.getByPlaceholder('Min. 8 characters').fill(E2E_USER.password)
  await page.getByPlaceholder('••••••••').fill(E2E_USER.password)
  await page.getByRole('button', { name: /create account/i }).click()

  let authed = await waitForAuthed()
    .then(() => true)
    .catch(() => false)

  // 2. Fall back to login when the user already exists (or register otherwise failed).
  if (!authed) {
    await page.goto('/login', { waitUntil: 'domcontentloaded' })
    await page.getByPlaceholder('you@company.com').fill(E2E_USER.email)
    await page.getByPlaceholder('••••••••').fill(E2E_USER.password)
    await page.getByRole('button', { name: /continue to workspace/i }).click()
    authed = await waitForAuthed()
      .then(() => true)
      .catch(() => false)
  }

  if (!authed) {
    await browser.close()
    throw new Error(
      'global-setup: failed to authenticate the shared E2E user via the UI ' +
        '(register and login both did not yield a stored aip_access_token). ' +
        'Check the auth endpoints are reachable from the E2E frontend.',
    )
  }

  // 3. Persist the authenticated session for every test.
  await context.storageState({ path: STORAGE_STATE })
  await browser.close()
}
