import { expect, test } from './fixtures'

// v1 review/score 0.9, v2 none, v3 0.7; plus the built-in Evaluators on every version.
test.use({ seed: 'support_metrics' })

test('Evaluator metric columns can be added to the version table and sorted', async ({ page }) => {
  await page.goto('/ui/kg/support/versions')
  const table = page.getByRole('table', { name: 'Ontology Versions' })
  const rows = table.getByRole('row')
  await expect(rows).toHaveCount(4)
  await expect(table.getByRole('columnheader', { name: 'review/score' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Metric columns' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'review/score' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'hierarchy/max_children' }).click()
  await page.keyboard.press('Escape')

  await expect(rows.first()).toHaveText(/Version.*Origin.*Created.*Aliases.*hierarchy\/max_children.*review\/score/)
  await expect(page).toHaveURL(/metric=review%2Fscore/)
  // Newest first, until sorted otherwise; a version without the metric shows a dash.
  await expect(rows.nth(1)).toHaveText(/^v3.*2\s*0\.7$/)
  await expect(rows.nth(2)).toHaveText(/^v2.*2\s*—$/)
  await expect(rows.nth(3)).toHaveText(/^v1.*1\s*0\.9$/)

  const score = table.getByRole('columnheader', { name: 'review/score' })
  await score.getByRole('button').click()
  await expect(score).toHaveAttribute('aria-sort', 'descending')
  await expect(rows.nth(1)).toHaveText(/^v1/)
  await expect(rows.nth(2)).toHaveText(/^v3/)
  await expect(rows.nth(3)).toHaveText(/^v2/)

  await score.getByRole('button').click()
  await expect(score).toHaveAttribute('aria-sort', 'ascending')
  await expect(rows.nth(1)).toHaveText(/^v3/)
  await expect(rows.nth(2)).toHaveText(/^v1/)
  await expect(rows.nth(3)).toHaveText(/^v2/)

  // The chosen columns are part of the URL.
  await page.reload()
  await expect(table.getByRole('columnheader', { name: 'review/score' })).toBeVisible()
})

test('the chart view shows one chart per Evaluator metric, and the search narrows them', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions')
  await page.getByRole('radio', { name: 'Chart' }).click()

  await expect(page).toHaveURL(/view=chart/)
  await expect(page.getByRole('table', { name: 'Ontology Versions' })).toHaveCount(0)
  const grid = page.getByRole('region', { name: 'Metric charts' })
  // 5 constraint_consistency + 4 hierarchy + 2 isolated_node_types + 4 orphan_concepts
  // + 3 redundancy + 5 structural_answerability + 1 review
  await expect(grid.getByRole('figure')).toHaveCount(24)
  const score = grid.getByRole('figure', { name: 'review/score' })
  await expect(score.getByText('v1')).toBeVisible()
  await expect(score.getByText('v3')).toBeVisible()

  await page.getByRole('searchbox', { name: 'Search metric charts' }).fill('RATIO')
  await expect(grid.getByRole('figure')).toHaveCount(3)
  await expect(grid.getByRole('figure', { name: 'structural_answerability/answerable_ratio' })).toBeVisible()

  await page.getByRole('searchbox', { name: 'Search metric charts' }).fill('nothing like this')
  await expect(grid.getByRole('figure')).toHaveCount(0)
  await expect(grid.getByText('No metric charts match “nothing like this”.')).toBeVisible()
})

test('the view mode survives a reload', async ({ page }) => {
  await page.goto('/ui/kg/support/versions?view=chart')
  await expect(page.getByRole('radio', { name: 'Chart' })).toBeChecked()
  await expect(page.getByRole('region', { name: 'Metric charts' })).toBeVisible()

  await page.reload()
  await expect(page.getByRole('region', { name: 'Metric charts' })).toBeVisible()

  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(page).not.toHaveURL(/view=chart/)
  await expect(page.getByRole('table', { name: 'Ontology Versions' })).toBeVisible()
})
