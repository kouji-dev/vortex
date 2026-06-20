/**
 * ModuleShell — the chat-style two-pane layout shared by Gateway / RAG /
 * Workers / Admin. Verifies each module renders the white left section-nav
 * (like the chat thread list) with an active row, plus the white ribbon header
 * reflecting the active section. Backend mocked via mock-server.mjs (owner role).
 */
import { test, expect } from '../support/fixtures'

type Case = {
  name: string
  url: string
  shellTestId: string
  moduleName: string
  activeLabel: string
}

const CASES: Case[] = [
  { name: 'Admin', url: '/admin/members', shellTestId: 'admin-shell', moduleName: 'Admin', activeLabel: 'Members' },
  { name: 'Gateway', url: '/gateway/overview', shellTestId: 'gateway-shell', moduleName: 'Gateway', activeLabel: 'Overview' },
  { name: 'Workers', url: '/workers/instances', shellTestId: 'workers-shell', moduleName: 'Workers', activeLabel: 'Workers' },
  { name: 'RAG', url: '/rag/kbs', shellTestId: 'rag-shell', moduleName: 'RAG', activeLabel: 'Knowledge bases' },
]

test.describe('ModuleShell — chat-style two-pane', () => {
  for (const c of CASES) {
    test(`${c.name} renders white section nav + ribbon`, async ({ page }) => {
      await page.goto(c.url, { waitUntil: 'domcontentloaded' })

      const shell = page.getByTestId(c.shellTestId)
      await expect(shell).toBeVisible()

      // Left pane: white nav with the module name header.
      const nav = shell.locator('.module-nav')
      await expect(nav).toBeVisible()
      await expect(nav.locator('.module-nav-title')).toHaveText(c.moduleName)

      // Active section row is highlighted.
      const active = nav.locator('.module-nav-item.active')
      await expect(active).toHaveCount(1)
      await expect(active).toContainText(c.activeLabel)

      // Right pane: white ribbon header reflects the active section.
      await expect(shell.locator('.module-ribbon-title')).toHaveText(c.activeLabel)
    })
  }
})
