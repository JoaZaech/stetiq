import { expect, test } from './fixtures'

test.describe('with Knowledge Graphs', () => {
  test.use({ seed: 'knowledge_graphs' })

  test('the landing page lists each Knowledge Graph with its state at a glance', async ({
    page,
  }) => {
    await page.goto('/ui/')
    const table = page.getByRole('table')

    await expect(table.getByRole('columnheader')).toHaveText([
      'Name',
      'Contract Alias version',
      'Latest version',
      'Last run',
      'Last modified',
    ])
    const support = table.getByRole('row', { name: /support/ })
    await expect(support.getByRole('cell')).toHaveText(['support', 'v1', 'v2', 'Finished', /\S/])
    const billing = table.getByRole('row', { name: /billing/ })
    await expect(billing.getByRole('cell')).toHaveText(['billing', 'v1', 'v1', 'Failed', /\S/])
  })

  test('searching by name filters the table', async ({ page }) => {
    await page.goto('/ui/')
    const table = page.getByRole('table')
    const search = page.getByRole('searchbox', { name: 'Search Knowledge Graphs' })
    await expect(table.getByRole('row', { name: /support/ })).toBeVisible()

    await search.fill('bill')

    await expect(table.getByRole('row', { name: /billing/ })).toBeVisible()
    await expect(table.getByRole('row', { name: /support/ })).toHaveCount(0)

    await search.fill('nothing-like-it')

    await expect(page.getByText('No Knowledge Graph matches “nothing-like-it”')).toBeVisible()
  })

  test('the search is kept in the URL, so a filtered list can be shared', async ({ page }) => {
    await page.goto('/ui/?q=sup')

    await expect(page.getByRole('searchbox', { name: 'Search Knowledge Graphs' })).toHaveValue('sup')
    await expect(page.getByRole('table').getByRole('row', { name: /billing/ })).toHaveCount(0)
  })

  test('each name links to its Knowledge Graph', async ({ page }) => {
    await page.goto('/ui/')

    await page.getByRole('table').getByRole('link', { name: 'support' }).click()

    // A Knowledge Graph opens on its first section.
    await expect(page).toHaveURL('/ui/kg/support/versions')
  })
})

test('an empty database shows how to register the first Ontology Version', async ({ page }) => {
  await page.goto('/ui/')

  await expect(page.getByText('No Knowledge Graphs yet')).toBeVisible()
  const snippet = page.getByRole('code').filter({ hasText: 'create_knowledge_graph(' })
  await expect(snippet).toContainText('stetiq.Client()')
  await expect(page.getByRole('table')).toHaveCount(0)
})
