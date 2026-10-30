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

test('the Ontology Version table lists versions newest first with Alias chips and a Candidate badge', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions')
  const table = page.getByRole('table', { name: 'Ontology Versions' })
  const rows = table.getByRole('row')

  await expect(rows.first()).toHaveText(/Version.*Origin.*Created.*Aliases/)
  await expect(rows).toHaveCount(4)
  await expect(rows.nth(1)).toHaveText(/v3.*run.*Candidate/)
  await expect(rows.nth(2)).toHaveText(/v2.*registered.*staging/)
  await expect(rows.nth(3)).toHaveText(/v1.*registered.*production/)
  await expect(rows.nth(2)).not.toHaveText(/Candidate/)
  await expect(rows.nth(3).getByText('production')).toHaveAccessibleDescription('Contract Alias')
  await expect(rows.nth(2).getByText('staging')).not.toHaveAccessibleDescription('Contract Alias')

  await rows.nth(2).getByRole('link', { name: 'v2' }).click()
  await expect(page).toHaveURL('/ui/kg/support/versions/2')
})
