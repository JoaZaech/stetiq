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
