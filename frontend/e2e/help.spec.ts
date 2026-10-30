import { expect, test } from './fixtures'

test('/ui/help opens the first guide page, with breadcrumbs and a table of contents in order', async ({
  page,
}) => {
  await page.goto('/ui/help')

  await expect(page).toHaveURL('/ui/help/getting-started')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Getting started')
  await expect(page).toHaveTitle('Getting started · stetiq')
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
    /^Help\s*Getting started$/,
  )
  const contents = page.getByRole('navigation', { name: 'Guide' }).getByRole('link')
  await expect(contents.nth(0)).toHaveText('Getting started')
  await expect(contents.nth(1)).toHaveText('Concepts')
  await expect(contents.nth(0)).toHaveAttribute('aria-current', 'page')
  await expect(contents.nth(1)).not.toHaveAttribute('aria-current', 'page')
})

test('the table of contents lists Using the web UI, which opens its page', async ({ page }) => {
  await page.goto('/ui/help/getting-started')
  const contents = page.getByRole('navigation', { name: 'Guide' })

  await contents.getByRole('link', { name: 'Using the web UI' }).click()

  await expect(page).toHaveURL('/ui/help/using-the-web-ui')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Using the web UI')
  await expect(page.getByRole('heading', { name: 'What needs edit access' })).toBeVisible()
})

test('the sidebar Help entry opens Help and is highlighted there', async ({ page }) => {
  await page.goto('/ui/')
  const help = page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Help' })
  await expect(help).not.toHaveAttribute('target', '_blank')

  await help.click()

  await expect(page).toHaveURL('/ui/help/getting-started')
  await expect(help).toHaveAttribute('data-active', 'true')
})

test('a link to another guide page navigates inside the app; an external link opens a new tab', async ({
  page,
}) => {
  await page.goto('/ui/help/getting-started')
  // A full page load would drop this marker; an in-app navigation keeps it.
  await page.evaluate(() => ((window as { inApp?: boolean }).inApp = true))
  const body = page.getByRole('article')

  const github = body.getByRole('link', { name: 'GitHub' })
  await expect(github).toHaveAttribute('target', '_blank')
  await expect(github).toHaveAttribute('href', /^https:\/\/github\.com\//)

  await body.getByRole('link', { name: 'Concepts' }).first().click()

  await expect(page).toHaveURL('/ui/help/concepts')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Concepts')
  expect(await page.evaluate(() => (window as { inApp?: boolean }).inApp)).toBe(true)
  const contents = page.getByRole('navigation', { name: 'Guide' })
  await expect(contents.getByRole('link', { name: 'Concepts' })).toHaveAttribute(
    'aria-current',
    'page',
  )
})

test('a heading anchor deep link scrolls to its section, and headings link to themselves', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  await page.goto('/ui/help/getting-started#track-your-first-construction-run')

  const heading = page.getByRole('heading', { name: 'Track your first Construction Run' })
  await expect(heading).toBeInViewport()
  await expect(heading.getByRole('link')).toHaveAttribute(
    'href',
    '#track-your-first-construction-run',
  )
})

test('a guide link with an anchor opens that section of the other page', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  await page.goto('/ui/help/concepts')

  await page.getByRole('article').getByRole('link', { name: 'Getting started' }).click()

  await expect(page).toHaveURL('/ui/help/getting-started#track-your-first-construction-run')
  await expect(
    page.getByRole('heading', { name: 'Track your first Construction Run' }),
  ).toBeInViewport()
})

test('a guide page renders tables and syntax-highlighted code', async ({ page }) => {
  await page.goto('/ui/help/getting-started')
  const body = page.getByRole('article')

  const table = body.getByRole('table')
  await expect(table.getByRole('columnheader')).toHaveText(['Setting', 'Default', 'What it does'])
  await expect(table.getByRole('row').filter({ hasText: '$STETIQ_ACTOR' })).toBeVisible()

  const python = body.locator('pre code.language-python')
  await expect(python).toContainText('client.start_run')
  // Highlighted: keywords sit in their own coloured span.
  const keyword = python.locator('.hljs-keyword').first()
  await expect(keyword).toBeVisible()
  const color = (el: Element) => getComputedStyle(el).color
  expect(await keyword.evaluate(color)).not.toBe(await python.evaluate(color))
})

test('an unknown guide page shows the not-found page', async ({ page }) => {
  await page.goto('/ui/help/no-such-page')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found')
})

test('a mermaid block renders as a diagram', async ({ page }) => {
  await page.goto('/ui/help/getting-started')

  const diagram = page.getByRole('article').getByRole('figure')
  await expect(diagram.locator('svg')).toBeVisible()
  await expect(diagram).toContainText('Install stetiq')
  await expect(diagram.locator('pre')).toHaveCount(0)
})

test('a diagram that does not parse shows its source and an error note', async ({ page }) => {
  // Break the Getting started diagram (bundled at build time) by unclosing a node label.
  await page.route('**/ui/assets/*.js', async (route) => {
    const response = await route.fetch()
    const body = (await response.text()).replace('[Install stetiq]', '[Install stetiq')
    await route.fulfill({ response, body })
  })
  await page.goto('/ui/help/getting-started')

  const diagram = page.getByRole('article').getByRole('figure')
  await expect(diagram.locator('pre code')).toContainText('install[Install stetiq -->')
  await expect(diagram).toContainText("This diagram couldn't be drawn")
  await expect(diagram.locator('svg')).toHaveCount(0)
})

test('diagrams are redrawn in the colours of the current theme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/ui/help/getting-started')
  const shapes = page.getByRole('article').getByRole('figure').locator('svg .node :is(rect, path)')
  // Relative luminance of the first filled node shape, 0 (black) to 1 (white); NaN while
  // none is drawn, so the poll waits.
  const lightness = () =>
    shapes.evaluateAll((els) => {
      const fill = els.map((el) => getComputedStyle(el).fill).find((f) => f.startsWith('rgb'))
      const [r, g, b] = fill?.match(/\d+/g)?.map(Number) ?? [NaN, NaN, NaN]
      return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    })
  await expect.poll(lightness).toBeGreaterThan(0.6)

  await page.emulateMedia({ colorScheme: 'dark' })

  await expect.poll(lightness).toBeLessThan(0.4)
})

test('a Help page without diagrams does not load Mermaid', async ({ page }) => {
  const scripts: string[] = []
  page.on('request', (request) => {
    if (request.resourceType() === 'script') scripts.push(request.url())
  })
  const mermaidScripts = () => scripts.filter((url) => /mermaid/i.test(url))

  await page.goto('/ui/help/concepts')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Concepts')
  await page.waitForLoadState('networkidle')
  expect(mermaidScripts()).toEqual([])

  // A page with a diagram does load it, so the check above can fail.
  await page
    .getByRole('navigation', { name: 'Guide' })
    .getByRole('link', { name: 'Getting started' })
    .click()
  await expect(page.getByRole('article').getByRole('figure').locator('svg')).toBeVisible()
  expect(mermaidScripts()).not.toEqual([])
})
