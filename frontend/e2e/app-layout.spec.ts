import { expect, test } from './fixtures'

test('the sidebar leads to Knowledge Graphs and Settings, with breadcrumbs and a page title', async ({
  page,
}) => {
  await page.goto('/ui/')
  const sidebar = page.getByRole('navigation', { name: 'Main' })
  const breadcrumbs = page.getByRole('navigation', { name: 'breadcrumb' })

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graphs')
  await expect(breadcrumbs).toHaveText('Knowledge Graphs')

  await sidebar.getByRole('link', { name: 'Settings' }).click()

  await expect(page).toHaveURL('/ui/settings')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings')
  await expect(breadcrumbs).toHaveText('Settings')
  await expect(page).toHaveTitle('Settings · stetiq')

  await sidebar.getByRole('link', { name: 'Knowledge Graphs' }).click()

  await expect(page).toHaveURL(/\/ui\/?$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graphs')
})

test('the sidebar shows the stetiq logo and package version, and links to the docs', async ({
  page,
}) => {
  await page.goto('/ui/')

  await expect(page.getByRole('img', { name: 'stetiq' }).first()).toBeVisible()
  await expect(page.getByText(/^v\d+\.\d+\.\d+/)).toBeVisible()
  const docs = page.getByRole('link', { name: /Docs/ })
  await expect(docs).toHaveAttribute('href', /github\.com\/JoaZaech\/stetiq/)
  await expect(docs).toHaveAttribute('target', '_blank')
})

test('the logo is also the favicon', async ({ page, request }) => {
  await page.goto('/ui/')
  const href = await page.locator('link[rel=icon]').getAttribute('href')

  const icon = await request.get(href!)

  expect(icon.ok()).toBe(true)
  expect(await icon.text()).toContain('currentColor')
})

test('the sidebar collapses to icons and remembers it', async ({ page }) => {
  await page.goto('/ui/')
  const sidebar = page.getByRole('navigation', { name: 'Main' })
  const expandedWidth = (await sidebar.boundingBox())!.width

  await page.getByRole('button', { name: 'Toggle Sidebar' }).first().click()

  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThan(64)
  await sidebar.getByRole('link', { name: 'Settings' }).hover()
  await expect(page.getByRole('tooltip')).toHaveText('Settings')

  await page.reload()

  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThan(64)
  await page.getByRole('button', { name: 'Toggle Sidebar' }).first().click()
  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBe(expandedWidth)
})

test('a deep link opens its page directly, and an unknown one says so', async ({ page }) => {
  await page.goto('/ui/settings')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings')

  await page.goto('/ui/no/such/page')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found')
})
