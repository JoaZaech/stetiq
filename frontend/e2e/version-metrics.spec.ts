import { expect, test } from './fixtures'

// v1 review/score 0.9, v2 none, v3 0.7; plus the built-in Evaluators on every version.
test.use({ seed: 'support_metrics' })

test('Evaluator metric columns can be added to the version table and sorted', async ({ page }) => {
  await page.goto('/ui/kg/support/versions')
  const table = page.getByRole('table', { name: 'Ontology Versions' })
  const rows = table.getByRole('row')
  await expect(rows).toHaveCount(4)
  await expect(table.getByRole('columnheader', { name: 'review/score' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Columns' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'review/score' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'hierarchy/max_children' }).click()
  await page.keyboard.press('Escape')

  await expect(rows.first()).toHaveText(/Version.*Origin.*Created.*Aliases.*hierarchy\/max_children.*review\/score/)
  await expect(page).toHaveURL(/col=metric%3Areview%2Fscore/)
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
  // 5 constraint_consistency + 3 definitions + 4 hierarchy + 2 isolated_node_types
  // + 4 orphan_concepts + 3 redundancy + 7 structural_answerability
  // + 4 competency_question_coverage + 1 review
  await expect(grid.getByRole('figure')).toHaveCount(33)
  const score = grid.getByRole('figure', { name: 'review/score' })
  await expect(score.getByText('v1')).toBeVisible()
  await expect(score.getByText('v3')).toBeVisible()

  await page.getByRole('searchbox', { name: 'Search metric charts' }).fill('RATIO')
  await expect(grid.getByRole('figure')).toHaveCount(5)
  await expect(grid.getByRole('figure', { name: 'structural_answerability/answerable_ratio' })).toBeVisible()
  await expect(grid.getByRole('figure', { name: 'definitions/definition_ratio' })).toBeVisible()

  await page.getByRole('searchbox', { name: 'Search metric charts' }).fill('nothing like this')
  await expect(grid.getByRole('figure')).toHaveCount(0)
  await expect(grid.getByText('No metric charts match “nothing like this”.')).toBeVisible()
})

test('a version’s Overview leads with its Gate result, then one card per Evaluator, the raw table behind a toggle', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions/3')
  const main = page.getByRole('main').last()
  await expect(main.getByRole('heading', { level: 2 }).first()).toHaveText('Gate result')

  // v3 is gated by three metric Gates: review-floor fails, the others are folded.
  const gate = page.getByRole('region', { name: 'Gate result' })
  await expect(gate).toContainText('1 of 3 Gates failed')
  const failed = gate.getByRole('list', { name: 'Failed Gates' })
  await expect(failed.locator(':scope > li')).toHaveText([/review-floor\s*review\.score = 0\.7 < min 0\.8/])
  await expect(gate.getByRole('list', { name: 'Passed Gates' })).toBeHidden()
  await gate.getByRole('button', { name: '2 passed' }).click()
  await expect(gate.getByRole('list', { name: 'Passed Gates' }).getByRole('listitem')).toHaveText([
    'shallow-hierarchy',
    'no-inconsistencies',
  ])

  // Built-in Evaluators under readable titles, ratios as percentages; a user's own by its raw name.
  const evaluators = page.getByRole('region', { name: 'Evaluator results' })
  const answerable = evaluators.getByRole('article', { name: 'Answerable questions' })
  await expect(answerable).toContainText(/structural_answerability\s*Answerable\s*\d+ \/ \d+\s*Unanswerable\s*\d+/)
  await expect(evaluators.getByRole('article', { name: 'Concepts with a Definition' })).toContainText(/Defined\s*[\d.]+%/)
  await expect(evaluators.getByRole('article', { name: 'Class hierarchy' })).toContainText(/Max depth\s*\d+\s*Root Classes\s*\d+/)
  await expect(evaluators.getByRole('article', { name: 'review' })).toHaveText(/^review\s*score\s*0\.7$/)
  await expect(evaluators.getByRole('article')).toHaveCount(9)

  await answerable.getByRole('button', { name: 'About Answerable questions' }).hover()
  await expect(page.getByRole('tooltip')).toContainText('Competency Questions whose Concepts this Ontology has')

  // The raw table is unchanged, one toggle away.
  const table = evaluators.getByRole('table', { name: 'Evaluator results' })
  await expect(table).toBeHidden()
  await evaluators.getByRole('button', { name: 'Show all metrics' }).click()
  await expect(table.getByRole('row').first()).toHaveText(/Evaluator.*Metric.*Value.*Use Case Version/)
  await expect(table.getByRole('row').filter({ hasText: 'review' })).toHaveText(/review\s*score\s*0\.7\s*—$/)

  // Details sit last, folded.
  const details = page.getByRole('region', { name: 'Details' })
  await expect(details.getByText('Content hash')).toBeHidden()
  await details.getByRole('button', { name: 'Details' }).click()
  await expect(details).toContainText(/Origin\s*run/)
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
