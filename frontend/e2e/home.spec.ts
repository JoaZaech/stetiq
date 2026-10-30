import { expect, test } from './fixtures'

test('Home welcomes the user at /, with a "Home" breadcrumb', async ({ page }) => {
  await page.goto('/ui/')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome to stetiq')
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText('Home')
  await expect(page).toHaveTitle('Home · stetiq')
})

const GUIDE_CARDS = [
  ['Declare an Ontology', '/ui/help/concepts#knowledge-graphs-and-ontology-versions'],
  ['Construction Runs', '/ui/help/concepts#construction-runs-and-conformance'],
  ['Use Cases & Evaluation', '/ui/help/concepts#evaluators-and-use-cases'],
  ['Observations & Drift', '/ui/help/concepts#observation-and-drift'],
  ['Promotions & Aliases', '/ui/help/concepts#aliases-and-promotion'],
] as const

test('Getting Started has five cards, each opening its user-guide page', async ({ page }) => {
  await page.goto('/ui/')
  const gettingStarted = page.getByRole('region', { name: 'Getting Started' })

  const cards = gettingStarted.getByRole('link')
  await expect(cards).toHaveCount(GUIDE_CARDS.length)
  for (const [i, [name, href]] of GUIDE_CARDS.entries()) {
    await expect(cards.nth(i).getByRole('heading')).toHaveText(name)
    await expect(cards.nth(i)).toHaveAttribute('href', href)
  }

  await cards.nth(1).click()

  await expect(page).toHaveURL('/ui/help/concepts#construction-runs-and-conformance')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Concepts')
})

test('Getting Started stays collapsed after a reload', async ({ page }) => {
  await page.goto('/ui/')
  const toggle = page.getByRole('button', { name: 'Getting Started' })
  const cards = page.getByRole('region', { name: 'Getting Started' }).getByRole('link')
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(cards.first()).toBeVisible()

  await toggle.click()

  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(cards).toHaveCount(0)

  await page.reload()

  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(cards).toHaveCount(0)

  await toggle.click()

  await expect(cards).toHaveCount(GUIDE_CARDS.length)
})

test.describe('with Knowledge Graphs', () => {
  test.use({ seed: 'many_knowledge_graphs' })

  test('Recent Knowledge Graphs shows the five last modified, with the list page’s columns', async ({
    page,
  }) => {
    await page.goto('/ui/')
    const recent = page.getByRole('region', { name: 'Recent Knowledge Graphs' })
    const table = recent.getByRole('table')

    await expect(table.getByRole('columnheader')).toHaveText([
      'Name',
      'Contract Alias version',
      'Latest version',
      'Last run',
      'Last modified',
    ])
    const rows = table.getByRole('row')
    await expect(rows).toHaveCount(6)
    await expect(rows.nth(1).getByRole('cell')).toHaveText(['beta', 'v1', 'v2', 'No runs', /\S/])
    for (const [i, name] of ['golf', 'foxtrot', 'echo', 'delta'].entries()) {
      await expect(rows.nth(i + 2).getByRole('cell').first()).toHaveText(name)
    }

    await table.getByRole('link', { name: 'beta' }).click()

    await expect(page).toHaveURL('/ui/kg/beta/versions')
  })

  test('"View all" on Recent Knowledge Graphs opens the full list at /kg', async ({ page }) => {
    await page.goto('/ui/')

    await page
      .getByRole('region', { name: 'Recent Knowledge Graphs' })
      .getByRole('link', { name: 'View all' })
      .click()

    await expect(page).toHaveURL('/ui/kg')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graphs')
    await expect(page.getByRole('table').getByRole('row')).toHaveCount(8)
  })
})

test('with no Knowledge Graphs, Home shows how to create one from the Python SDK', async ({
  page,
}) => {
  await page.goto('/ui/')
  const recent = page.getByRole('region', { name: 'Recent Knowledge Graphs' })

  await expect(recent.getByText('No Knowledge Graphs yet')).toBeVisible()
  const snippet = recent.getByRole('code').filter({ hasText: 'create_knowledge_graph(' })
  await expect(snippet).toContainText('stetiq.Client()')
  await expect(recent.getByRole('table')).toHaveCount(0)
})
