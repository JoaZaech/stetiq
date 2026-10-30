import { expect, test } from './fixtures'

test.use({ seed: 'support_lineage' })

const SECTIONS = ['Ontology Versions', 'Construction Runs', 'Use Case', 'Observations', 'Promotions']

test('a Knowledge Graph shows its sections in the sidebar and its header', async ({ page }) => {
  await page.goto('/ui/kg/support')

  await expect(page).toHaveURL('/ui/kg/support/versions')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
  const header = page.getByRole('region', { name: 'Knowledge Graph' })
  await expect(header.getByText('Evolution Mode')).toBeVisible()
  await expect(header.getByText('evolving')).toBeVisible()
  await expect(header.getByText('Contract Alias')).toBeVisible()
  await expect(header.getByText('production → v1')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
    /Knowledge Graphs.*support.*Ontology Versions/,
  )

  const sections = page.getByRole('navigation', { name: 'Knowledge Graph' })
  for (const name of SECTIONS) await expect(sections.getByRole('link', { name })).toBeVisible()
  await expect(sections.getByRole('link', { name: 'Ontology Versions' })).toHaveAttribute(
    'aria-current',
    'page',
  )

  await sections.getByRole('link', { name: 'Promotions' }).click()
  await expect(page).toHaveURL('/ui/kg/support/promotions')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
  await expect(page.getByRole('heading', { level: 2 })).toHaveText('Promotions')

  await page.getByRole('link', { name: 'Back to Knowledge Graphs' }).click()
  await expect(page).toHaveURL(/\/ui\/?$/)
  await expect(page.getByRole('navigation', { name: 'Knowledge Graph' })).toHaveCount(0)
})
