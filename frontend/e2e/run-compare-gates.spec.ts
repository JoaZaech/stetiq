import { expect, test } from './fixtures'

const short = (id: unknown) => String(id).slice(0, 8)
const compareUrl = (...ids: unknown[]) => `/ui/kg/support/runs/compare?${ids.map((id) => `id=${String(id)}`).join('&')}`

test.describe('a gated Knowledge Graph', () => {
  // `support`, gated by conformance-floor (>= 0.6), review-score (`review
  // (min_confidence=0.5)/score` >= 0.8), no-breaking-changes and no-count-drop:
  // `baseline` (recorded: Conformance fail, review 0.9 pass), then previews of
  // `regressed` (Conformance fail, review 0.6 fail), `unreviewed` (Conformance pass, no
  // review result, count drop fails) and `improved` (every Gate passes).
  test.use({ seed: 'gates' })

  test('each gated KPI cell shows its verdict, recorded or previewed, and each KPI a summary', async ({
    page,
    stetiq,
  }) => {
    const { baseline, regressed, unreviewed, improved } = stetiq.seeded
    await page.goto(compareUrl(baseline, regressed, unreviewed, improved))
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare 4 Construction Runs')

    await expect(page.getByRole('note', { name: 'Gate Preview source' })).toHaveText(
      new RegExp(`judged against current Gates.*Construction Run ${short(baseline)}`),
    )

    const overview = page.getByRole('table', { name: 'Runs' })
    const conformance = overview.getByRole('row', { name: /^Conformance/ })
    await expect(conformance).toHaveText(
      /0\.5455\s*fail\s*recorded\s*0\.5455\s*fail\s*preview\s*0\.75\s*pass\s*preview\s*0\.75\s*pass\s*preview/,
    )
    await expect(conformance.getByRole('rowheader')).toContainText('50% pass')
    await expect(conformance.getByRole('img', { name: '2 of 4 runs pass, 2 fail' })).toBeVisible()
    await expect(overview.getByRole('cell').getByTitle('judged against current Gates').first()).toHaveText('preview')

    const evaluations = page.getByRole('table', { name: 'Evaluator results' })
    const review = evaluations.getByRole('row', { name: /^review \(min_confidence=0\.5\)\/score/ })
    await expect(review).toHaveText(/0\.9\s*pass\s*recorded\s*0\.6\s*fail\s*preview\s*no result\s*preview\s*0\.95\s*pass\s*preview/)
    await expect(review.getByRole('rowheader')).toContainText('50% pass')
    await expect(review.getByRole('img', { name: '2 of 4 runs pass, 1 fail, 1 no result' })).toBeVisible()

    // KPIs no Gate covers stay neutral: another configuration, and the pipeline's metrics.
    const ungated = evaluations.getByRole('row', { name: /^review \(min_confidence=0\.8\)\/score/ })
    await expect(ungated).toHaveText(/0\.5\s*0\.5\s*—\s*0\.5$/)
    await expect(page.getByRole('table', { name: 'Metrics' })).not.toContainText(/pass|fail/)
  })

  test('the Gates section lists every Gate and whether all passed, per run', async ({ page, stetiq }) => {
    const { baseline, regressed, unreviewed, improved } = stetiq.seeded
    await page.goto(compareUrl(baseline, regressed, unreviewed, improved))
    const gates = page.getByRole('table', { name: 'Gates' })
    await expect(gates.getByRole('row', { name: /^conformance-floor/ })).toHaveText(
      /fail\s*recorded\s*fail\s*preview\s*pass\s*preview\s*pass\s*preview/,
    )
    await expect(gates.getByRole('row', { name: /^review-score/ })).toHaveText(/pass.*fail.*fail.*pass/)
    await expect(gates.getByRole('row', { name: /^no-breaking-changes/ })).toHaveText(/pass.*pass.*pass.*pass/)
    await expect(gates.getByRole('row', { name: /^no-count-drop/ })).toHaveText(/pass.*pass.*fail.*pass/)
    await expect(gates.getByRole('row', { name: /^All Gates passed/ })).toHaveText(
      /fail\s*recorded\s*fail\s*preview\s*fail\s*preview\s*pass\s*preview/,
    )

    // "Show diff only" hides the Gates and KPIs every run agrees on.
    await page.getByRole('switch', { name: 'Show diff only' }).click()
    await expect(gates).not.toContainText('no-breaking-changes')
    await expect(gates).toContainText('no-count-drop')
    await expect(page.getByRole('table', { name: 'Runs' })).toContainText(/Conformance.*fail/)
    await page.goto(`${compareUrl(baseline, regressed)}&diff=only`)
    await expect(page.getByRole('table', { name: 'Runs' })).not.toContainText('Conformance')
    await expect(gates).not.toContainText('conformance-floor')
    await expect(gates.getByRole('row', { name: /^review-score/ })).toHaveText(/pass\s*recorded\s*fail\s*preview/)
  })
})

test.describe('the KPI drill-down', () => {
  // As above; the gated `review (min_confidence=0.5)` result has detail items about its
  // `score` (`open-tickets`) and about a `confidence` metric, the other configuration
  // one about its own `score` (`other-configuration`).
  test.use({ seed: 'gates' })

  test('a KPI cell opens a side sheet with the value, verdict, Gate reasons and detail items', async ({
    page,
    stetiq,
  }) => {
    const { baseline, regressed } = stetiq.seeded
    await page.goto(compareUrl(baseline, regressed))
    const review = page
      .getByRole('table', { name: 'Evaluator results' })
      .getByRole('row', { name: /^review \(min_confidence=0\.5\)\/score/ })
    await review.getByRole('button', { name: `review (min_confidence=0.5)/score of run ${short(regressed)}` }).click()

    const sheet = page.getByRole('dialog', { name: 'review (min_confidence=0.5)/score' })
    await expect(sheet).toContainText(`Construction Run ${String(regressed)}`)
    await expect(sheet.getByRole('definition').first()).toHaveText('0.6')
    await expect(sheet.getByRole('region', { name: 'Verdict' })).toContainText(/fail\s*preview.*judged against current Gates/)
    const reasons = sheet.getByRole('list', { name: 'review-score reasons' })
    await expect(reasons.getByRole('listitem')).toHaveText(['review.score = 0.6 < min 0.8', 'open-tickets: no answer'])
    const details = sheet.getByRole('list', { name: 'Detail items' })
    await expect(details.getByRole('listitem')).toHaveText([/open-tickets\s*no answer/])
    await sheet.getByRole('link', { name: 'Open the run’s Evaluations tab' }).click()
    await expect(page).toHaveURL(new RegExp(`/runs/${String(regressed)}/evaluations$`))
  })

  test('a gated KPI the run has no value for says "no result" once, as its value', async ({ page, stetiq }) => {
    const { baseline, unreviewed } = stetiq.seeded
    await page.goto(compareUrl(baseline, unreviewed))
    await page.getByRole('button', { name: `review (min_confidence=0.5)/score of run ${short(unreviewed)}` }).click()

    const sheet = page.getByRole('dialog', { name: 'review (min_confidence=0.5)/score' })
    await expect(sheet.getByRole('definition').first()).toHaveText('no result')
    const verdict = sheet.getByRole('region', { name: 'Verdict' })
    await expect(verdict).toContainText(/preview.*judged against current Gates/)
    await expect(verdict).not.toContainText('no result')
  })

  test('Conformance opens with its recorded verdict and links to the Conformance tab; an ungated KPI opens with no verdict', async ({
    page,
    stetiq,
  }) => {
    const { baseline, regressed } = stetiq.seeded
    await page.goto(compareUrl(baseline, regressed))
    await page.getByRole('button', { name: `Conformance of run ${short(baseline)}` }).click()
    const sheet = page.getByRole('dialog', { name: 'Conformance' })
    await expect(sheet.getByRole('region', { name: 'Verdict' })).toContainText(/fail\s*recorded.*recorded Gate result/)
    await expect(sheet.getByRole('list', { name: 'conformance-floor reasons' })).toContainText('Conformance 0.5455 < 0.6')
    await expect(sheet.getByRole('link', { name: 'Open the run’s Conformance tab' })).toHaveAttribute(
      'href',
      new RegExp(`/runs/${String(baseline)}/conformance$`),
    )
    await page.keyboard.press('Escape')

    await page.getByRole('button', { name: `review (min_confidence=0.8)/score of run ${short(regressed)}` }).click()
    const ungated = page.getByRole('dialog', { name: 'review (min_confidence=0.8)/score' })
    await expect(ungated.getByRole('definition').first()).toHaveText('0.5')
    await expect(ungated.getByRole('region', { name: 'Verdict' })).toHaveText(/No Gate covers this KPI/)
    await expect(ungated.getByRole('list', { name: 'Detail items' }).getByRole('listitem')).toHaveText([
      /other-configuration/,
    ])
  })
})

test.describe('a Knowledge Graph never gated', () => {
  // `support` with two reviewed runs, `first` and `second`, and no Gate result.
  test.use({ seed: 'never_gated' })

  test('every KPI is neutral, with a hint on turning verdicts on', async ({ page, stetiq }) => {
    const { first, second } = stetiq.seeded
    await page.goto(compareUrl(first, second))
    await expect(page.getByRole('note', { name: 'Gates' })).toHaveText(/stetiq\.yaml.*stetiq gate/)
    await expect(page.getByRole('table', { name: 'Evaluator results' })).toContainText(/review \(min_confidence=0\.5\)\/score\s*0\.9\s*0\.6/)
    await expect(page.getByRole('table', { name: 'Runs' })).not.toContainText(/pass|fail/)
    await expect(page.getByRole('table', { name: 'Evaluator results' })).not.toContainText(/pass|fail/)
    await expect(page.getByRole('table', { name: 'Gates' })).toHaveCount(0)
  })
})
