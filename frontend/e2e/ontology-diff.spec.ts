import { expect, test } from './fixtures'

test.use({ seed: 'support_breaking_change' })

test('selecting two versions and clicking Compare shows the classified Ontology Diff at a shareable URL', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions')
  const compare = page.getByRole('button', { name: 'Compare' })
  await expect(compare).toBeDisabled()

  await page.getByRole('checkbox', { name: 'Select v4' }).check()
  await expect(compare).toBeDisabled()
  await page.getByRole('checkbox', { name: 'Select v2' }).check()
  await compare.click()

  await expect(page).toHaveURL('/ui/kg/support/versions/compare?id=2&id=4')
  const expectDiff = async () => {
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare v2 → v4')
    await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
      /Knowledge Graphs.*support.*Ontology Versions.*Compare/,
    )
    const diff = page.getByRole('region', { name: 'Ontology Diff' })
    await expect(diff.getByText('Overall: breaking')).toBeVisible()
    const rows = diff.getByRole('table', { name: 'Changes' }).getByRole('row')
    await expect(rows).toHaveCount(4)
    await expect(rows.nth(1)).toHaveText(/breaking.*removed.*Ticket\.opened_at/)
    await expect(rows.nth(2)).toHaveText(/deprecating.*deprecated.*Agent/)
    await expect(rows.nth(3)).toHaveText(/additive.*added.*ASSIGNED/)
  }
  await expectDiff()

  // The URL alone reproduces the comparison, e.g. when a colleague opens it.
  await page.reload()
  await expectDiff()
  await page.getByRole('link', { name: 'v2', exact: true }).click()
  await expect(page).toHaveURL('/ui/kg/support/versions/2')
})

test('comparing a version with itself shows no changes', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/compare?id=3&id=3')

  await expect(page.getByRole('region', { name: 'Ontology Diff' })).toContainText(
    'No changes between v3 and v3.',
  )
})

test('comparing an unknown version says so', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/compare?id=2&id=9')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ontology Version not found')
})

test('the Changes tab shows the Ontology Diff against the previous version', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/4')
  await page.getByRole('link', { name: 'Changes' }).click()

  await expect(page).toHaveURL('/ui/kg/support/versions/4/changes')
  await expect(page.getByRole('link', { name: 'Changes' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByText('Changes from v3')).toBeVisible()
  const diff = page.getByRole('region', { name: 'Ontology Diff' })
  await expect(diff.getByText('Overall: breaking')).toBeVisible()
  await expect(diff.getByRole('row', { name: /Ticket\.priority/ })).toHaveText(/breaking.*removed/)

  await page.goto('/ui/kg/support/versions/1/changes')
  await expect(
    page.getByText('v1 is the first Ontology Version: there is nothing to compare it with.'),
  ).toBeVisible()
})
