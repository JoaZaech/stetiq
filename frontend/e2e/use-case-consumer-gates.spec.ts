import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

// plant_consumer_gates: the Reliability dashboard's triage-rows-hold failed on run 2
// (breakdown-technicians 5 → 2 rows), the Maintenance assistant's gate passed, the Safety
// team's was never evaluated and the Planning team declares none.
test.use({ seed: 'plant_consumer_gates' })

const card = (page: Page, name: string) =>
  page.getByRole('region', { name: 'Consumers' }).getByRole('article', { name })
const gateSection = (page: Page, name: string) => card(page, name).getByRole('region', { name: 'Consumer Gate' })

test('a Consumer card shows its declared Consumer Gate and the failed verdict with the rows it lost', async ({
  page,
  stetiq,
}) => {
  await page.goto('/ui/kg/plant/use-case')

  const section = gateSection(page, 'Reliability dashboard')
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

  const passed = gateSection(page, 'Maintenance assistant').getByRole('group', { name: 'Latest verdict' })
  await expect(passed).toContainText('Passed')
  await expect(passed.getByRole('list', { name: 'Failing Competency Questions' })).toHaveCount(0)

  const safety = gateSection(page, 'Safety team')
  await expect(safety.getByRole('listitem')).toHaveText([/row_count_drop.*audit-machines.*no drop in rows/])
  await expect(safety).toContainText('Not evaluated yet')
  await expect(safety).not.toContainText(/Passed|Failed/)

  const planning = gateSection(page, 'Planning team')
  await expect(planning).toContainText('None declared')
  await expect(planning).not.toContainText(/Passed|Failed|Not evaluated yet/)
})

test('each Consumer card badges evaluation on each Observation as planned, and keeps the Connector planned', async ({
  page,
}) => {
  await page.goto('/ui/kg/plant/use-case')

  for (const name of ['Reliability dashboard', 'Planning team']) {
    const c = card(page, name)
    await expect(c.getByRole('link', { name: 'Planned: Evaluated on each Observation', exact: true })).toHaveAttribute(
      'href',
      '/ui/help/vision#consumer-gate',
    )
    await expect(c.getByRole('group', { name: 'Connector', exact: true })).toHaveText('Connector: not connected')
  }
})
