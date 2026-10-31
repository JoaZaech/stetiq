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
