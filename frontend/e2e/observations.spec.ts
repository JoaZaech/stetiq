import { expect, test } from './fixtures'

test.describe('with Drift', () => {
  test.use({ seed: 'observed_support' })

  test('Observations are a timeline of rows, newest first, each with its status, time and run', async ({
    page,
    stetiq,
  }) => {
    await page.goto('/ui/kg/support/observations')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('Observations')

    const rows = page.getByRole('list', { name: 'Observations' }).getByRole('listitem')
    await expect(rows).toHaveCount(2)
    const [onDemand, fromRun] = [rows.nth(0), rows.nth(1)]
    await expect(onDemand).toHaveText(/^Drift\s*\S.*on demand/)
    await expect(onDemand.locator('time')).toHaveAttribute('datetime', /^\d{4}-\d{2}-\d{2}T/)
    const runId = stetiq.seeded.run_id as string
    await expect(fromRun).toHaveText(new RegExp(`^No Drift.*from run ${runId.slice(0, 8)}$`))
    await expect(fromRun.getByRole('link', { name: runId.slice(0, 8) })).toHaveAttribute(
      'href',
      `/ui/kg/support/runs/${runId}`,
    )
  })

  test('only a Drift row expands, to its Contract Alias, version, thresholds and findings', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    const rows = page.getByRole('list', { name: 'Observations' }).getByRole('listitem')
    const [onDemand, fromRun] = [rows.nth(0), rows.nth(1)]

    await expect(fromRun.getByRole('button')).toHaveCount(0)
    await expect(fromRun.getByRole('region', { name: 'Drift' })).toHaveCount(0)

    const toggle = onDemand.getByRole('button', { name: 'Drift details' })
    const drift = onDemand.getByRole('region', { name: 'Drift' })
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(drift).toBeHidden()
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')

    await expect(drift).toContainText(/Contract Alias\s*production/)
    await expect(drift).toContainText(/Ontology Version\s*v1/)
    await expect(drift.getByRole('link', { name: 'v1' })).toHaveAttribute('href', '/ui/kg/support/versions/1')
    await expect(drift).toContainText(/Thresholds\s*max count drop off · max count increase 50%/)

    // Concept kinds in the glossary's words: Class, Relation, Attribute.
    await expect(drift.getByRole('list', { name: 'Drift findings' }).getByRole('listitem')).toHaveText([
      /^Refund Class — observed but not declared$/,
      /^Ticket\.channel Attribute — observed but not declared$/,
      /^ESCALATED Relation — observed but not declared$/,
      /^count rose: Ticket Class — count rose from 1 to 4 \(\+300%\)$/,
    ])
    await expect(drift).not.toContainText(/node type|relationship type|property/)

    await toggle.click()
    await expect(drift).toBeHidden()
    await expect(page.getByText('The Knowledge Graph matches the Ontology Version of its Contract Alias')).toHaveCount(0)
  })
})

test.describe('without Drift', () => {
  test.use({ seed: 'support_lineage' })

  test('no Drift shows the empty state', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    const rows = page.getByRole('list', { name: 'Observations' }).getByRole('listitem')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toHaveText(/^No Drift/)
    await expect(page.getByText('No Drift. The Knowledge Graph matches the Ontology Version of its Contract Alias.')).toBeVisible()
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
