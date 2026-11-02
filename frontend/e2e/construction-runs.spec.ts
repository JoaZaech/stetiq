import { expect, signIn, test } from './fixtures'

test.describe('with Construction Runs', () => {
  test.use({ seed: 'construction_runs' })

  test('the run table lists runs, newest first, with params, status, Conformance, Gate and links', async ({
    page,
    stetiq,
  }) => {
    await page.goto('/ui/kg/support/runs')
    const table = page.getByRole('table', { name: 'Construction Runs' })
    const rows = table.getByRole('row')

    // `extractor` is a column from the start; other params are added with Columns.
    await expect(rows.first()).toHaveText(
      /Run.*extractor.*Status.*Started.*Duration.*Declared Ontology.*Conformance.*Gate.*Candidate/,
    )
    await expect(rows).toHaveCount(3)
    const aborted = String(stetiq.seeded.aborted)
    const finished = String(stetiq.seeded.finished)
    // `support` was never gated: no Gate result and no Gate Preview.
    await expect(rows.nth(1)).toHaveText(new RegExp(`^${aborted.slice(0, 8)}rules.*Failed.*v1.*—.*—.*—`))
    // The evolving run is judged against its Candidate v2.
    await expect(rows.nth(2)).toHaveText(new RegExp(`^${finished.slice(0, 8)}llm.*Finished.*v1.*81\\.8%.*—.*v2`))
    await expect(page.getByText('2 runs', { exact: true })).toBeVisible()

    // Search matches a run's id, param values and versions, and is kept in the URL.
    await page.getByRole('searchbox', { name: 'Search runs' }).fill('rules')
    await expect(page).toHaveURL(/q=rules/)
    await expect(rows).toHaveCount(2)
    await expect(page.getByText('1 of 2 runs')).toBeVisible()
    await page.getByRole('searchbox', { name: 'Search runs' }).fill('')
    await expect(rows).toHaveCount(3)

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
    await expect(header).not.toHaveText(/temperature|recall/)

    await page.getByRole('button', { name: 'Columns' }).click()
    // A default column is not offered again.
    await expect(page.getByRole('menuitemcheckbox', { name: 'extractor' })).toHaveCount(0)
    await page.getByRole('menuitemcheckbox', { name: 'temperature' }).click()
    await page.getByRole('menuitemcheckbox', { name: 'recall' }).click()
    await page.keyboard.press('Escape')
    await expect(header).toHaveText(/temperature.*recall/)
    const finished = table.getByRole('row').filter({ hasText: String(stetiq.seeded.finished).slice(0, 8) })
    await expect(finished).toHaveText(/0\.2.*0\.8/)

    await page.getByRole('radiogroup', { name: 'Status' }).getByRole('radio', { name: 'Failed' }).click()
    await page.getByRole('radiogroup', { name: 'Started' }).getByRole('radio', { name: 'Last 24 hours' }).click()
    await expect(page).toHaveURL(/status=failed/)
    await expect(page).toHaveURL(/range=24h/)
    await expect(table.getByRole('row')).toHaveCount(2)
    await expect(table.getByRole('row').nth(1)).toHaveText(/rules.*Failed/)

    // A shared link opens the same view.
    await page.reload()
    await expect(header).toHaveText(/temperature.*recall/)
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

    const heading = page.getByRole('heading', { level: 1 })
    await expect(heading).toHaveText(id.slice(0, 8))
    // The four evaluation KPIs every evaluated page shares, in the same order.
    const kpis = page.getByRole('list', { name: 'Evaluation' }).getByRole('listitem')
    await expect(kpis).toHaveText([/^Conformance\s*81\.8%/, /^CQ coverage\s*1\/2/, /^Gates\s*—/, /^Drift/])
    await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
      new RegExp(`Knowledge Graphs.*support.*Construction Runs.*${id.slice(0, 8)}`),
    )
    await expect(page.getByRole('main').getByText('Finished')).toBeVisible()
    await expect(
      page.getByRole('navigation', { name: 'Construction Run' }).getByRole('link', { name: 'Overview' }),
    ).toHaveAttribute('aria-current', 'page')

    // The full id is in Details, with a copy button.
    const details = page.getByRole('region', { name: 'Details' })
    await expect(details).toContainText(`Run id${id}`)
    await details.getByRole('button', { name: 'Copy run id' }).click()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(id)
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

  test('the Evaluation tab lists the Conformance findings in one table, judged against the Candidate', async ({
    page,
    stetiq,
  }) => {
    await page.goto(`/ui/kg/support/runs/${String(stetiq.seeded.finished)}`)
    await page.getByRole('link', { name: 'Evaluation', exact: true }).click()
    await expect(page).toHaveURL(/\/evaluation$/)

    const note = page.getByRole('note', { name: 'Judged against' })
    await expect(note).toContainText('Judged against Candidate v2')
    const findings = page.getByRole('table', { name: 'Findings' })
    await expect(findings.getByRole('row')).toHaveCount(3)
    await expect(findings.getByRole('row').nth(1)).toHaveText(/Party\s*Class\s*Declared but not observed/)
    await expect(findings.getByRole('row').nth(2)).toHaveText(/Party\.name\s*Attribute\s*Declared but not observed/)
    // ESCALATED, Ticket.priority and their pattern are Candidate v2's additions, not mismatches.
    await expect(findings).not.toContainText('Observed but not declared')

    // The Kind filter narrows the table.
    await page.getByRole('button', { name: 'Kind: All' }).click()
    await page.getByRole('menuitemradio', { name: /Attribute/ }).click()
    await expect(findings.getByRole('row')).toHaveCount(2)

    await note.getByRole('link', { name: 'v2' }).click()
    await expect(page).toHaveURL('/ui/kg/support/versions/2')
    // Neither Competency Question needs ESCALATED or Ticket.priority.
    await expect(
      page.getByRole('region', { name: 'Evaluator results' }).getByRole('article', { name: 'Unjustified additions' }),
    ).toContainText(/Unjustified\s*2 \/ 2/)
  })

  test('the Evaluation tab shows Evaluator cards and each executed Competency Question, never row data', async ({
    page,
    stetiq,
  }) => {
    const id = String(stetiq.seeded.finished)
    // The old Evaluations tab's link leads to the Evaluation tab.
    await page.goto(`/ui/kg/support/runs/${id}/evaluations`)
    await expect(page).toHaveURL(`/ui/kg/support/runs/${id}/evaluation`)
    await expect(page.getByRole('link', { name: 'Evaluation', exact: true })).toHaveAttribute('aria-current', 'page')

    const evaluators = page.getByRole('region', { name: 'Evaluator results' })
    await expect(evaluators.getByRole('article', { name: 'Questions executed' })).toContainText(
      /Passed\s*1 \/ 2\s*Failed\s*1/,
    )
    await expect(evaluators.getByRole('article', { name: 'Conformance' })).toContainText(/Score\s*81\.8%/)
    await expect(evaluators.getByRole('article', { name: 'Observed graph' })).toBeVisible()
    await expect(evaluators.getByRole('article', { name: 'review (min_confidence=0.5)' })).toContainText('0.9')

    // The raw table is behind the toggle.
    const results = evaluators.getByRole('table', { name: 'Evaluator results' })
    await expect(results).toBeHidden()
    await evaluators.getByRole('button', { name: 'Show all metrics' }).click()
    await expect(results).toContainText(/competency_question_execution\s*pass_ratio\s*0\.5\s*1/)
    await expect(results).toContainText(/conformance\s*score\s*0\.8182/)
    await expect(results).toContainText(/observed_schema\s*node_types\s*2/)

    const questions = page.getByRole('list', { name: 'Competency Questions' }).getByRole('listitem')
    await expect(questions).toHaveText([
      /^What are our customers called\?\s*Passed$/,
      /^Which tickets are open\?\s*Error$/,
    ])

    // The canned query returned a customer's name: instance data stays out of the UI.
    await expect(page.locator('body')).not.toContainText('Ada')

    // A row opens the question's sheet, with this run's check and error type.
    await questions.nth(1).getByRole('button').click()
    await expect(page).toHaveURL(`/ui/kg/support/runs/${id}/evaluation?sheet=question%3Aopen-tickets`)
    const sheet = page.getByRole('dialog', { name: 'Which tickets are open?' })
    const inThisRun = sheet.getByRole('region', { name: 'In this run' })
    await expect(inThisRun).toContainText(/Result\s*Error\s*Check\s*non-empty result\s*Error type\s*ValueError/)
    await expect(sheet.getByRole('region', { name: 'Author details' })).toContainText('open-tickets')
    await expect(sheet.getByRole('button', { name: 'Edit' })).toHaveCount(0)
    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()
    await expect(page).toHaveURL(`/ui/kg/support/runs/${id}/evaluation`)
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
    await expect(alert).toHaveText('Failed before the Graph Source was observed.')
    await expect(page.getByRole('region', { name: 'Details' })).toContainText(/Candidate\s*None/)
    await page.getByRole('link', { name: 'Evaluation', exact: true }).click()
    await expect(page.getByRole('main').last()).toContainText('No Conformance')
    await expect(page.getByRole('main').last()).toContainText('No Evaluator results for this run.')
  })

  test('a run that failed under strict Evolution Mode says why', async ({ page, stetiq }) => {
    await page.goto(`/ui/kg/orders/runs/${String(stetiq.seeded.strict_failed)}`)
    await expect(page.getByRole('main').getByText('Failed', { exact: true })).toBeVisible()
    const alert = page.getByRole('alert')
    await expect(alert).toContainText(/Failed: \d+ Concepts? observed but not declared \(strict mode\)\./)
    // Show opens the Evaluation tab's findings, filtered to those.
    await alert.getByRole('link', { name: 'Show' }).click()
    await expect(page).toHaveURL(/\/evaluation\?finding=Observed\+but\+not\+declared$/)
    await expect(page.getByRole('button', { name: 'Finding: Observed but not declared' })).toBeVisible()
    await expect(page.getByRole('note', { name: 'Judged against' })).toHaveCount(0)
    const findings = page.getByRole('table', { name: 'Findings' })
    await expect(findings).toContainText('ESCALATED')
    await expect(findings).not.toContainText('Declared but not observed')
  })

  test('an unknown run id, or a run of another Knowledge Graph, is not found', async ({ page, stetiq }) => {
    await page.goto('/ui/kg/support/runs/0123456789abcdef')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
    await page.goto(`/ui/kg/support/runs/${String(stetiq.seeded.strict_failed)}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Construction Run not found')
  })
})

test.describe('with Gates', () => {
  // `support`, gated by conformance-floor (>= 0.6) and review-score (`review
  // (min_confidence=0.5)/score` >= 0.8): `baseline` (recorded: Conformance fail, review 0.9
  // pass), then previews of `regressed` (Conformance fail, review 0.6 fail), `unreviewed`
  // (Conformance pass, no review result) and `improved` (both pass).
  test.use({ seed: 'gates' })

  test('the chart view draws each Gate bound and colours points by their verdict, recorded or previewed', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/runs?view=chart')
    const grid = page.getByRole('region', { name: 'Metric charts' })
    await expect(page.getByRole('note', { name: 'Gate Preview source' })).toContainText('judged against current Gates')

    const conformance = grid.getByRole('figure', { name: 'Conformance', exact: true })
    await expect(conformance.getByRole('list', { name: 'Bounds' })).toHaveText('conformance-floor: min 0.6')
    await expect(conformance.locator('.recharts-reference-line')).toHaveCount(1)
    await expect(conformance.getByRole('note')).toHaveText('Verdicts: 1 recorded, 3 preview')
    await expect(conformance.getByRole('button', { name: /0\.5455, fail \(recorded\)$/ })).toHaveCount(1)
    await expect(conformance.getByRole('button', { name: /0\.5455, fail \(preview\)$/ })).toHaveCount(1)
    await expect(conformance.getByRole('button', { name: /0\.75, pass \(preview\)$/ })).toHaveCount(2)

    // `unreviewed` has no review result, so no point.
    const review = grid.getByRole('figure', { name: 'review (min_confidence=0.5)/score' })
    await expect(review.getByRole('list', { name: 'Bounds' })).toHaveText('review-score: min 0.8')
    await expect(review.getByRole('button', { name: /, (pass|fail) \((recorded|preview)\)$/ })).toHaveCount(3)
    await expect(review.getByRole('button', { name: /0\.6, fail \(preview\)$/ })).toBeVisible()
    await expect(review.getByRole('button', { name: /0\.95, pass \(preview\)$/ })).toBeVisible()

    // No Gate covers `precision` or the other review configuration: neutral points, no bound.
    for (const name of ['precision', 'review (min_confidence=0.8)/score']) {
      const ungated = grid.getByRole('figure', { name, exact: true })
      await expect(ungated.getByRole('button', { name: /^.+: \d/ }).first()).toBeVisible()
      await expect(ungated.getByRole('button', { name: /pass|fail/ })).toHaveCount(0)
      await expect(ungated.getByRole('list', { name: 'Bounds' })).toHaveCount(0)
      await expect(ungated.locator('.recharts-reference-line')).toHaveCount(0)
    }
  })
})

test.describe('the KPI drill-down from the chart view', () => {
  // The `gates` seed, as above.
  test.use({ seed: 'gates' })

  test('a chart point opens the side sheet for its run and KPI', async ({ page, stetiq }) => {
    const { regressed } = stetiq.seeded
    await page.goto('/ui/kg/support/runs?view=chart')
    const review = page
      .getByRole('region', { name: 'Metric charts' })
      .getByRole('figure', { name: 'review (min_confidence=0.5)/score' })
    await review.getByRole('button', { name: /0\.6, fail \(preview\)$/ }).click()

    const sheet = page.getByRole('dialog', { name: 'review (min_confidence=0.5)/score' })
    await expect(sheet).toContainText(`Construction Run ${String(regressed)}`)
    await expect(sheet.getByRole('definition').first()).toHaveText('0.6')
    await expect(sheet.getByRole('region', { name: 'Verdict' })).toContainText(/fail\s*preview/)
    await expect(sheet.getByRole('list', { name: 'review-score reasons' })).toContainText('review.score = 0.6 < min 0.8')
    await expect(sheet.getByRole('list', { name: 'Detail items' }).getByRole('listitem')).toHaveText([/open-tickets/])
    await expect(sheet.getByRole('link', { name: 'Open the run’s Evaluation tab' })).toBeVisible()
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
    await expect(page.getByRole('heading', { level: 1 })).toContainText(finished.slice(0, 8))
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
