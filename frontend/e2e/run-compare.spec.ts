import { expect, test } from './fixtures'

// `support`: `finished` (llm, temperature 0.2, precision 0.91, recall 0.8), `aborted`
// (rules, failed) and `rerun` (llm, temperature 0.5, precision 0.85, recall 0.8);
// `orders`: `strict_failed`.
test.use({ seed: 'compared_runs' })

const short = (id: unknown) => String(id).slice(0, 8)

test('selected runs compare side by side, from a URL that can be shared', async ({ page, stetiq }) => {
  const { finished, rerun } = stetiq.seeded
  await page.goto('/ui/kg/support/runs')
  const compare = page.getByRole('button', { name: 'Compare' })
  await expect(compare).toBeDisabled()
  await page.getByRole('checkbox', { name: `Select run ${short(rerun)}` }).check()
  await expect(compare).toBeDisabled()
  await page.getByRole('checkbox', { name: `Select run ${short(finished)}` }).check()
  await compare.click()

  // Oldest run first.
  await expect(page).toHaveURL(`/ui/kg/support/runs/compare?id=${String(finished)}&id=${String(rerun)}`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare 2 Construction Runs')
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
    /Knowledge Graphs.*support.*Construction Runs.*Compare/,
  )

  const overview = page.getByRole('table', { name: 'Runs' })
  await expect(overview.getByRole('row').first()).toHaveText(new RegExp(`${short(finished)}.*${short(rerun)}`))
  await expect(overview).toContainText(/Status\s*Finished\s*Finished/)
  await expect(overview).toContainText(/Declared Ontology\s*v1\s*v1/)
  await expect(overview).toContainText(/Conformance\s*0\.5455\s*0\.5455/)
  const params = page.getByRole('table', { name: 'Params' })
  await expect(params).toContainText(/extractor\s*llm\s*llm/)
  await expect(params).toContainText(/temperature\s*0\.2\s*0\.5/)
  const metrics = page.getByRole('table', { name: 'Metrics' })
  await expect(metrics).toContainText(/precision\s*0\.91\s*0\.85/)
  await expect(metrics).toContainText(/recall\s*0\.8\s*0\.8/)
  const evaluations = page.getByRole('table', { name: 'Evaluator results' })
  await expect(evaluations).toContainText(/competency_question_execution\/pass_ratio\s*0\.5\s*0\.5/)

  await overview.getByRole('link', { name: short(rerun) }).click()
  await expect(page).toHaveURL(`/ui/kg/support/runs/${String(rerun)}`)
  await page.goBack()

  // A shared link opens the same comparison.
  await page.reload()
  await expect(params).toContainText(/temperature\s*0\.2\s*0\.5/)
})

test('"Show diff only" hides the rows whose values are identical', async ({ page, stetiq }) => {
  const { finished, rerun, aborted } = stetiq.seeded
  await page.goto(`/ui/kg/support/runs/compare?id=${String(finished)}&id=${String(rerun)}&id=${String(aborted)}`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare 3 Construction Runs')
  const params = page.getByRole('table', { name: 'Params' })
  await expect(params).toContainText(/extractor\s*llm\s*llm\s*rules/)

  await page.goto(`/ui/kg/support/runs/compare?id=${String(finished)}&id=${String(rerun)}`)
  const overview = page.getByRole('table', { name: 'Runs' })
  const metrics = page.getByRole('table', { name: 'Metrics' })
  await page.getByRole('switch', { name: 'Show diff only' }).click()
  await expect(page).toHaveURL(/diff=only/)

  await expect(params).not.toContainText('extractor')
  await expect(params).toContainText(/temperature\s*0\.2\s*0\.5/)
  await expect(metrics).not.toContainText('recall')
  await expect(metrics).toContainText(/precision\s*0\.91\s*0\.85/)
  await expect(overview).not.toContainText('Declared Ontology')
  await expect(overview).toContainText('Started')
  await expect(page.getByRole('table', { name: 'Evaluator results' })).toContainText('No differences.')

  await page.reload()
  await expect(page.getByRole('switch', { name: 'Show diff only' })).toBeChecked()
  await expect(params).not.toContainText('extractor')
  await page.getByRole('switch', { name: 'Show diff only' }).click()
  await expect(params).toContainText('extractor')
})

test('comparing runs of another Knowledge Graph, or unknown runs, is not found', async ({ page, stetiq }) => {
  const { finished, strict_failed } = stetiq.seeded
  await page.goto(`/ui/kg/support/runs/compare?id=${String(finished)}&id=${String(strict_failed)}`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
  await page.goto(`/ui/kg/support/runs/compare?id=${String(finished)}&id=0123456789abcdef`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
})

test('the chart view shows one chart per run metric, Conformance and Evaluator result metric, over start time', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/runs')
  await page.getByRole('radio', { name: 'Chart' }).click()
  await expect(page).toHaveURL(/view=chart/)
  await expect(page.getByRole('table', { name: 'Construction Runs' })).toHaveCount(0)

  const grid = page.getByRole('region', { name: 'Metric charts' })
  for (const name of ['Conformance', 'precision', 'recall', 'review (min_confidence=0.5)/score', 'review (min_confidence=0.8)/score']) {
    await expect(grid.getByRole('figure', { name, exact: true })).toBeVisible()
  }
  await page.getByRole('searchbox', { name: 'Search metric charts' }).fill('recall')
  await expect(grid.getByRole('figure')).toHaveCount(1)

  await page.reload()
  await expect(page.getByRole('radio', { name: 'Chart' })).toBeChecked()
  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(page.getByRole('table', { name: 'Construction Runs' })).toBeVisible()
})
