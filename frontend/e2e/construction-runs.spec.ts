import { expect, signIn, test } from './fixtures'

test.describe('with Construction Runs', () => {
  test.use({ seed: 'construction_runs' })

  test('the run table lists runs, newest first, with status, Conformance and links', async ({
    page,
    stetiq,
  }) => {
    await page.goto('/ui/kg/support/runs')
    const table = page.getByRole('table', { name: 'Construction Runs' })
    const rows = table.getByRole('row')

    await expect(rows.first()).toHaveText(
      /Run.*Status.*Started.*Duration.*Declared Ontology.*Conformance.*Candidate/,
    )
    await expect(rows).toHaveCount(3)
    const aborted = String(stetiq.seeded.aborted)
    const finished = String(stetiq.seeded.finished)
    await expect(rows.nth(1)).toHaveText(new RegExp(`${aborted.slice(0, 8)}.*Failed.*v1.*—.*—`))
    await expect(rows.nth(2)).toHaveText(new RegExp(`${finished.slice(0, 8)}.*Finished.*v1.*0\\.5455.*v2`))

    await rows.nth(2).getByRole('link', { name: 'v2' }).click()
    await expect(page).toHaveURL('/ui/kg/support/versions/2')
    await page.goBack()
    await rows.nth(2).getByRole('link', { name: 'v1' }).click()
    await expect(page).toHaveURL('/ui/kg/support/versions/1')
    await page.goBack()
    await rows.nth(2).getByRole('link', { name: finished.slice(0, 8) }).click()
    await expect(page).toHaveURL(`/ui/kg/support/runs/${finished}`)
  })

  test('param and metric columns can be added, and filters are kept in the URL', async ({
    page,
    stetiq,
  }) => {
    await page.goto('/ui/kg/support/runs')
    const table = page.getByRole('table', { name: 'Construction Runs' })
    const header = table.getByRole('row').first()
    await expect(header).not.toHaveText(/extractor|recall/)

    await page.getByRole('button', { name: 'Columns' }).click()
    await page.getByRole('menuitemcheckbox', { name: 'extractor' }).click()
    await page.getByRole('menuitemcheckbox', { name: 'recall' }).click()
    await page.keyboard.press('Escape')
    await expect(header).toHaveText(/extractor.*recall/)
    const finished = table.getByRole('row').filter({ hasText: String(stetiq.seeded.finished).slice(0, 8) })
    await expect(finished).toHaveText(/llm.*0\.8/)

    await page.getByRole('radiogroup', { name: 'Status' }).getByRole('radio', { name: 'Failed' }).click()
    await page.getByRole('radiogroup', { name: 'Started' }).getByRole('radio', { name: 'Last 24 hours' }).click()
    await expect(page).toHaveURL(/status=failed/)
    await expect(page).toHaveURL(/range=24h/)
    await expect(table.getByRole('row')).toHaveCount(2)
    await expect(table.getByRole('row').nth(1)).toHaveText(/Failed.*rules/)

    // A shared link opens the same view.
    await page.reload()
    await expect(header).toHaveText(/extractor.*recall/)
    await expect(table.getByRole('row')).toHaveCount(2)
    await page.getByRole('radiogroup', { name: 'Status' }).getByRole('radio', { name: 'Running' }).click()
    await expect(table).toContainText('No Construction Run matches these filters.')
  })

  test('the run page Overview shows provenance, params, metrics and the ending Observation', async ({
    page,
    context,
    stetiq,
  }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    const id = String(stetiq.seeded.finished)
    await page.goto(`/ui/kg/support/runs/${id}`)

    await expect(page.getByRole('heading', { level: 1 })).toHaveText(id)
    await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
      new RegExp(`Knowledge Graphs.*support.*Construction Runs.*${id.slice(0, 8)}`),
    )
    await expect(page.getByRole('main').getByText('Finished')).toBeVisible()
    await page.getByRole('button', { name: 'Copy run id' }).click()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(id)
    await expect(page.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')

    const details = page.getByRole('region', { name: 'Details' })
    await expect(details).toContainText(/Duration\s*\d/)
    await details.getByRole('link', { name: 'v1' }).click()
    await expect(page).toHaveURL('/ui/kg/support/versions/1')
    await page.goBack()
    await details.getByRole('link', { name: 'v2' }).click()
    await expect(page).toHaveURL('/ui/kg/support/versions/2')
    await page.goBack()

    const params = page.getByRole('table', { name: 'Params' })
    await expect(params.getByRole('row').nth(1)).toHaveText(/extractor\s*llm/)
    await expect(params.getByRole('row').nth(2)).toHaveText(/temperature\s*0\.2/)
    const metrics = page.getByRole('table', { name: 'Metrics' })
    await expect(metrics.getByRole('row').nth(1)).toHaveText(/precision\s*0\.91/)
    await expect(metrics.getByRole('row').nth(2)).toHaveText(/recall\s*0\.8/)

    const observation = page.getByRole('region', { name: 'Observation' })
    await expect(observation).toContainText(/Graph Source\s*database neo4j/)
    await expect(observation).toContainText(/Classes\s*2/)
    await expect(observation).toContainText(/Relations\s*2/)
  })

  test('the Conformance tab shows the score and the per-Concept breakdown', async ({ page, stetiq }) => {
    await page.goto(`/ui/kg/support/runs/${String(stetiq.seeded.finished)}`)
    await page.getByRole('link', { name: 'Conformance' }).click()
    await expect(page).toHaveURL(/\/conformance$/)

    await expect(page.getByRole('region', { name: 'Score' })).toContainText('0.5455')
    const absent = page.getByRole('table', { name: 'Declared but not observed' })
    await expect(absent.getByRole('row')).toHaveCount(3)
    await expect(absent.getByRole('row').nth(1)).toHaveText(/Party\s*class/)
    await expect(absent.getByRole('row').nth(2)).toHaveText(/Party\.name\s*attribute/)
    const undeclared = page.getByRole('table', { name: 'Observed but not declared' })
    await expect(undeclared.getByRole('row')).toHaveCount(3)
    await expect(undeclared.getByRole('row').nth(1)).toHaveText(/ESCALATED\s*relation/)
    await expect(undeclared.getByRole('row').nth(2)).toHaveText(/Ticket\.priority\s*attribute/)
    const patterns = page.getByRole('table', { name: 'Other mismatches' })
    await expect(patterns.getByRole('row').nth(1)).toHaveText(
      /\(Ticket\)-\[ESCALATED\]->\(Customer\)\s*pattern\s*Observed but not declared/,
    )
  })

  test('the Evaluations tab shows Evaluator results and each executed Competency Question, never row data', async ({
    page,
    stetiq,
  }) => {
    await page.goto(`/ui/kg/support/runs/${String(stetiq.seeded.finished)}/evaluations`)
    await expect(page.getByRole('link', { name: 'Evaluations' })).toHaveAttribute('aria-current', 'page')

    const results = page.getByRole('table', { name: 'Evaluator results' })
    await expect(results).toContainText(/competency_question_execution\s*pass_ratio\s*0\.5\s*1/)
    await expect(results).toContainText(/conformance\s*score\s*0\.5455/)
    await expect(results).toContainText(/observed_schema\s*node_types\s*2/)

    const questions = page.getByRole('table', { name: 'Competency Questions' })
    await expect(questions.getByRole('row').first()).toHaveText(/Competency Question.*Result.*Check.*Error type/)
    await expect(questions.getByRole('row').nth(1)).toHaveText(/customer-names\s*Passed\s*expected answer\s*—/)
    await expect(questions.getByRole('row').nth(2)).toHaveText(/open-tickets\s*Error\s*non-empty result\s*ValueError/)

    // The canned query returned a customer's name: instance data stays out of the UI.
    await expect(page.locator('body')).not.toContainText('Ada')
  })

  test('the chart view charts Evaluator results, one chart per parameter configuration, under the filters', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/runs?view=chart')
    const grid = page.getByRole('region', { name: 'Metric charts' })
    await expect(grid.getByRole('figure', { name: 'recall' })).toBeVisible()
    await expect(grid.getByRole('figure', { name: 'Conformance', exact: true })).toBeVisible()
    await expect(grid.getByRole('figure', { name: 'conformance/score' })).toBeVisible()
    await expect(grid.getByRole('figure', { name: 'competency_question_execution/pass_ratio' })).toBeVisible()

    await page.getByRole('searchbox', { name: 'Search metric charts' }).fill('review')
    await expect(grid.getByRole('figure')).toHaveCount(2)
    await expect(grid.getByRole('figure', { name: 'review (min_confidence=0.5)/score' })).toBeVisible()
    await expect(grid.getByRole('figure', { name: 'review (min_confidence=0.8)/score' })).toBeVisible()

    // Only the aborted run failed in `support`, and it has no Evaluator results.
    await page.getByRole('radiogroup', { name: 'Status' }).getByRole('radio', { name: 'Failed' }).click()
    await expect(grid.getByRole('figure')).toHaveCount(0)
  })

  test('a run that failed before observing says so', async ({ page, stetiq }) => {
    await page.goto(`/ui/kg/support/runs/${String(stetiq.seeded.aborted)}`)
    const alert = page.getByRole('alert')
    await expect(alert).toContainText('This Construction Run failed')
    await expect(alert).toContainText('before its Graph Source was observed')
    await expect(page.getByRole('region', { name: 'Details' })).toContainText(/Candidate\s*None/)
    await page.getByRole('link', { name: 'Conformance' }).click()
    await expect(page.getByRole('main').last()).toContainText('No Conformance')
    await page.getByRole('link', { name: 'Evaluations' }).click()
    await expect(page.getByRole('main').last()).toContainText('No Evaluator results for this run.')
  })

  test('a run that failed under strict Evolution Mode says why', async ({ page, stetiq }) => {
    await page.goto(`/ui/kg/orders/runs/${String(stetiq.seeded.strict_failed)}`)
    await expect(page.getByRole('main').getByText('Failed', { exact: true })).toBeVisible()
    const alert = page.getByRole('alert')
    await expect(alert).toContainText('This Construction Run failed')
    await expect(alert).toContainText('Evolution Mode is strict')
    await page.getByRole('link', { name: 'Conformance' }).click()
    await expect(page.getByRole('table', { name: 'Observed but not declared' })).toContainText('ESCALATED')
  })

  test('an unknown run id, or a run of another Knowledge Graph, is not found', async ({ page, stetiq }) => {
    await page.goto('/ui/kg/support/runs/0123456789abcdef')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
    await page.goto(`/ui/kg/support/runs/${String(stetiq.seeded.strict_failed)}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
  })
})

test.describe('with a token that can read one Knowledge Graph', () => {
  test.use({ mode: 'server', seed: 'construction_runs_reader' })

  test('runs of a Knowledge Graph the user cannot read are not found', async ({ page, stetiq }) => {
    await signIn(page, (stetiq.seeded.grace as { value: string }).value)
    const strict = String(stetiq.seeded.strict_failed)
    await page.goto(`/ui/kg/support/runs/${strict}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
    await page.goto(`/ui/kg/orders/runs/${strict}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graph not found')

    const finished = String(stetiq.seeded.finished)
    await page.goto(`/ui/kg/support/runs/${finished}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(finished)
  })
})

test.describe('without Construction Runs', () => {
  // Knowledge Graphs `support` and `billing`, no runs.
  test.use({ seed: 'signed_in_users' })

  test('the run list shows the empty state', async ({ page }) => {
    await page.goto('/ui/kg/support/runs')
    await expect(page.getByRole('heading', { name: 'No Construction Runs yet' })).toBeVisible()
    await expect(page.getByText('client.start_run("support"')).toBeVisible()
    await expect(page.getByRole('table', { name: 'Construction Runs' })).toHaveCount(0)
  })
})
