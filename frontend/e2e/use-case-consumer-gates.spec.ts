import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// plant_consumer_gates: the Reliability dashboard's triage-rows-hold failed on run 2
// (breakdown-technicians 5 → 2 rows), the Maintenance assistant's gate passed, the Safety
// team's was never evaluated and the Planning team declares none.
test.use({ seed: 'plant_consumer_gates' })

const tile = (page: Page, name: string) =>
  page.getByRole('region', { name: 'Consumers' }).getByRole('article', { name })
/** Opens a Consumer's sheet and returns its Consumer Gate section. */
const gateSection = async (page: Page, name: string) => {
  await tile(page, name).getByRole('button', { name }).click()
  return page.getByRole('dialog', { name }).getByRole('region', { name: 'Consumer Gate' })
}

test('a tile shows its Consumer Gate’s latest verdict only when it declares one', async ({ page }) => {
  await page.goto('/ui/kg/plant/use-case')

  await expect(tile(page, 'Reliability dashboard')).toContainText('Consumer Gate failed')
  await expect(tile(page, 'Maintenance assistant')).toContainText('Consumer Gate passed')
  await expect(tile(page, 'Safety team')).toContainText('Consumer Gate not evaluated yet')
  await expect(tile(page, 'Planning team')).toBeVisible()
  await expect(tile(page, 'Planning team')).not.toContainText('Consumer Gate')
})

test('the Consumer sheet shows the declared Consumer Gate and the failed verdict with the rows it lost', async ({
  page,
  stetiq,
}) => {
  await page.goto('/ui/kg/plant/use-case')

  const section = await gateSection(page, 'Reliability dashboard')
  await expect(section.getByRole('list', { name: 'Declared Consumer Gates' }).getByRole('listitem')).toHaveText([
    /triage-rows-hold.*row_count_drop.*triage-breakdowns.*at most −10% rows/,
  ])
  await expect(section).toContainText('Declared in use-case.yaml')
  const verdict = section.getByRole('group', { name: 'Latest verdict' })
  await expect(verdict).toContainText('Failed')
  await expect(verdict).toContainText('Ontology Version 1')
  await expect(verdict).toContainText(`run ${(stetiq.seeded.candidate_run as string).slice(0, 8)}`)
  await expect(verdict).toContainText(/ago|just now/)
  await expect(verdict.getByRole('list', { name: 'Failing Competency Questions' }).getByRole('listitem')).toHaveText([
    /triage-breakdowns.*breakdown-technicians.*5 → 2 rows \(−60\.0%, limit −10%\)/,
  ])
})

test('a passing verdict, a gate never evaluated and a Consumer without gates read differently', async ({
  page,
}) => {
  await page.goto('/ui/kg/plant/use-case')

  const passed = (await gateSection(page, 'Maintenance assistant')).getByRole('group', { name: 'Latest verdict' })
  await expect(passed).toContainText('Passed')
  await expect(passed.getByRole('list', { name: 'Failing Competency Questions' })).toHaveCount(0)
  await page.keyboard.press('Escape')

  const safety = await gateSection(page, 'Safety team')
  await expect(safety.getByRole('listitem')).toHaveText([/row_count_drop.*audit-machines.*no drop in rows/])
  await expect(safety).toContainText('Not evaluated yet')
  await expect(safety).not.toContainText(/Passed|Failed/)
  await page.keyboard.press('Escape')

  const planning = await gateSection(page, 'Planning team')
  await expect(planning).toContainText('No Consumer Gate declared')
  await expect(planning).not.toContainText(/Passed|Failed|Not evaluated yet|use-case\.yaml/)
})

test('the Consumer sheet badges evaluation on each Observation as planned; the tile does not', async ({
  page,
}) => {
  await page.goto('/ui/kg/plant/use-case')

  for (const name of ['Reliability dashboard', 'Planning team']) {
    await expect(tile(page, name).getByRole('link', { name: /^Planned: Evaluated/ })).toHaveCount(0)
    const gate = await gateSection(page, name)
    await expect(
      gate.getByRole('link', { name: 'Planned: Evaluated on each Observation', exact: true }),
    ).toHaveAttribute('href', '/ui/help/vision#consumer-gate')
    await page.keyboard.press('Escape')
  }
})
