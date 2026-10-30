import { expect, test } from './fixtures'

const SECTIONS = ['Ontology Versions', 'Construction Runs', 'Use Case', 'Observations', 'Promotions']

test('the sidebar lists Home, the Knowledge Graph switcher, the five sections, Help and Settings', async ({
  page,
}) => {
  await page.goto('/ui/settings')
  const sidebar = page.getByRole('navigation', { name: 'Main' })

  await expect(sidebar.getByRole('listitem')).toHaveText([
    'Home',
    'Select a Knowledge Graph',
    ...SECTIONS,
    'Help',
    'Settings',
  ])
  await expect(sidebar.getByRole('button', { name: 'Select a Knowledge Graph' })).toBeVisible()
  await expect(sidebar.getByRole('link', { name: 'Knowledge Graphs' })).toHaveCount(0)
})

test('the app opens on Home; the sidebar leads to Settings and back Home, with breadcrumbs and a page title', async ({
  page,
}) => {
  await page.goto('/ui/')
  const sidebar = page.getByRole('navigation', { name: 'Main' })
  const breadcrumbs = page.getByRole('navigation', { name: 'breadcrumb' })

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome to stetiq')
  await expect(breadcrumbs).toHaveText('Home')
  await expect(sidebar.getByRole('link', { name: 'Home' })).toHaveAttribute('data-active', 'true')

  await sidebar.getByRole('link', { name: 'Settings' }).click()

  await expect(page).toHaveURL('/ui/settings')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings')
  await expect(breadcrumbs).toHaveText('Settings')
  await expect(page).toHaveTitle('Settings · stetiq')

  await sidebar.getByRole('link', { name: 'Home' }).click()

  await expect(page).toHaveURL(/\/ui\/?$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome to stetiq')

  await page.getByRole('link', { name: 'stetiq' }).first().click()

  await expect(page).toHaveURL(/\/ui\/?$/)
})

test.describe('with Knowledge Graphs', () => {
  test.use({ seed: 'knowledge_graphs' })

  test('on a fresh browser the section items are disabled, saying to select a Knowledge Graph first', async ({
    page,
  }) => {
    await page.goto('/ui/settings')
    const sidebar = page.getByRole('navigation', { name: 'Main' })

    for (const name of SECTIONS) {
      await expect(sidebar.getByRole('link', { name })).toBeDisabled()
      await expect(sidebar.getByRole('link', { name })).not.toHaveAttribute('href')
    }
    await sidebar.getByRole('link', { name: 'Construction Runs' }).hover()
    await expect(page.getByRole('tooltip')).toHaveText('Select a Knowledge Graph first')
  })

  test('outside a Knowledge Graph, the section items lead into the last one opened', async ({ page }) => {
    await page.goto('/ui/kg/billing/observations')
    const sidebar = page.getByRole('navigation', { name: 'Main' })
    await expect(sidebar.getByRole('link', { name: 'Observations' })).toHaveAttribute('aria-current', 'page')

    await sidebar.getByRole('link', { name: 'Settings' }).click()
    await expect(page).toHaveURL('/ui/settings')

    await expect(sidebar.getByRole('button', { name: 'Select a Knowledge Graph' })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: 'Ontology Versions' })).toHaveAttribute(
      'href',
      '/ui/kg/billing/versions',
    )

    await page.goto('/ui/')
    await sidebar.getByRole('link', { name: 'Construction Runs' }).click()

    await expect(page).toHaveURL('/ui/kg/billing/runs')
    await expect(sidebar.getByRole('button', { name: 'Knowledge Graph: billing' })).toBeVisible()
  })

  test('a last-opened Knowledge Graph that does not exist leaves the section items disabled', async ({
    page,
  }) => {
    await page.goto('/ui/kg/no-such-graph/runs')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graph not found')

    await page.goto('/ui/settings')

    const sidebar = page.getByRole('navigation', { name: 'Main' })
    await expect(sidebar.getByRole('link', { name: 'Construction Runs' })).toBeDisabled()
  })

  test('with the sidebar collapsed, the switcher is an icon whose tooltip names the Knowledge Graph', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions')
    const sidebar = page.getByRole('navigation', { name: 'Main' })

    await page.getByRole('button', { name: 'Toggle Sidebar' }).first().click()
    await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThan(64)

    await sidebar.getByRole('button', { name: 'Knowledge Graph: support' }).hover()
    await expect(page.getByRole('tooltip')).toHaveText('support')
  })
})

test('the sidebar shows the stetiq logo and package version, and links to Help', async ({
  page,
}) => {
  await page.goto('/ui/')

  await expect(page.getByRole('img', { name: 'stetiq' }).first()).toBeVisible()
  await expect(page.getByText(/^v\d+\.\d+\.\d+/)).toBeVisible()
  const help = page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Help' })
  await expect(help).toHaveAttribute('href', '/ui/help')
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
