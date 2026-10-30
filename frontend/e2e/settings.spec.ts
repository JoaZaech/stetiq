import { type Page } from '@playwright/test'
import { expect, test } from './fixtures'

/** The colour scheme the page renders native controls and colours in. */
const colorScheme = (page: Page) =>
  page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)

test.use({ actor: 'grace' })

test('Settings shows local mode under stetiq ui, where every Knowledge Graph is editable', async ({
  page,
}) => {
  await page.goto('/ui/settings')

  const access = page.getByRole('region', { name: 'Access' })
  await expect(access).toContainText('Local mode')
  await expect(access).toContainText('grace')
  await expect(access).toContainText('every Knowledge Graph is editable')
})

test('the theme follows the system by default and a choice is remembered', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/ui/settings')
  const theme = page.getByRole('radiogroup', { name: 'Theme' })

  await expect(theme.getByRole('radio', { name: 'System' })).toBeChecked()
  await expect.poll(() => colorScheme(page)).toBe('dark')

  await theme.getByRole('radio', { name: 'Light' }).click()

  await expect.poll(() => colorScheme(page)).toBe('light')
  await page.reload()
  await expect(theme.getByRole('radio', { name: 'Light' })).toBeChecked()
  await expect.poll(() => colorScheme(page)).toBe('light')

  await page.emulateMedia({ colorScheme: 'light' })
  await theme.getByRole('radio', { name: 'Dark' }).click()

  await expect.poll(() => colorScheme(page)).toBe('dark')
})
