import { test, expect } from '@playwright/test'

import { createEmptyConversation } from './helpers/create-conversation'

let kbName = ''

test.describe.configure({ mode: 'serial' })

test.describe('Chat knowledge bases', () => {
  test('create KB for chat tests', async ({ page }) => {
    kbName = `E2E Chat KB ${Date.now()}`
    await page.goto('/knowledge-bases')
    await page.getByRole('button', { name: /add knowledge base/i }).click()
    await page.getByLabel(/^name$/i).fill(kbName)
    await page.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page.getByRole('heading', { level: 1, name: kbName })).toBeVisible()
  })

  test('attach KB via picker', async ({ page, request }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`)

    await page.getByRole('button', { name: 'Knowledge bases' }).click()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()

    await page.getByRole('option', { name: new RegExp(kbName) }).click()
    await expect(page.getByText('Saving…')).toBeHidden({ timeout: 30_000 })

    await expect(
      page.getByRole('button', { name: /1 knowledge base active/i }),
    ).toBeVisible()

    await page.reload()
    await page.getByRole('button', { name: /1 knowledge base active/i }).click()
    const opt = page.getByRole('option', { name: new RegExp(kbName) })
    await expect(opt).toContainText('active')
  })
})
