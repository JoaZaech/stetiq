import { expect, test } from './fixtures'

test.describe('with Drift', () => {
  test.use({ seed: 'observed_support' })

  test('Observations are listed newest first with their scope and linked run', async ({
    page,
    stetiq,
  }) => {
    await page.goto('/ui/kg/support/observations')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('Observations')

    const observations = page.getByRole('article')
    await expect(observations).toHaveCount(2)
    const onDemand = observations.nth(0)
    const fromRun = observations.nth(1)
    for (const observation of [onDemand, fromRun]) {
      await expect(observation.getByRole('heading', { level: 3 })).toHaveText(/^Observation \w+/)
      await expect(observation).toContainText(/Graph Source scope\s*database neo4j · label Support/)
    }
    await expect(onDemand).toContainText(/Construction Run\s*None \(on demand\)/)
    const runLink = fromRun.getByRole('link', { name: stetiq.seeded.run_id as string })
    await expect(runLink).toHaveAttribute('href', `/ui/kg/support/runs/${stetiq.seeded.run_id}`)
  })

  test('a Drift event shows its Contract Alias, version, findings and thresholds', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    const [onDemand, fromRun] = [page.getByRole('article').nth(0), page.getByRole('article').nth(1)]

    const drift = onDemand.getByRole('region', { name: 'Drift' })
    await expect(drift).toContainText(/Contract Alias\s*production/)
    await expect(drift).toContainText(/Ontology Version\s*v1/)
    await expect(drift.getByRole('link', { name: 'v1' })).toHaveAttribute('href', '/ui/kg/support/versions/1')
    await expect(drift).toContainText(/Thresholds\s*max count drop off · max count increase 50%/)

    const findings = drift.getByRole('table', { name: 'Drift findings' })
    const rows = findings.getByRole('row')
    await expect(rows.first()).toHaveText(/Kind.*Concept.*Detail/)
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(1)).toHaveText(/undeclared.*Refund.*node type/)
    await expect(rows.nth(2)).toHaveText(/count increase.*Ticket.*count rose from 1 to 4/)

    await expect(fromRun.getByRole('region', { name: 'Drift' })).toHaveCount(0)
    await expect(fromRun).toContainText('No Drift')
    await expect(page.getByText('The graph matches its contract')).toHaveCount(0)
  })
})

test.describe('without Drift', () => {
  test.use({ seed: 'support_lineage' })

  test('no Drift shows the empty state', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    await expect(page.getByRole('article')).toHaveCount(1)
    await expect(page.getByText('No Drift. The graph matches its contract.')).toBeVisible()
  })
})

test.describe('never observed', () => {
  test.use({ seed: 'signed_in_users' })

  test('a Knowledge Graph without Observations says how to trigger one', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    await expect(page.getByText('No Observations yet.')).toBeVisible()
    await expect(page.getByText('stetiq observe')).toBeVisible()
  })
})
