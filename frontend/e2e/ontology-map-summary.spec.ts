import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_transit' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const summaryOf = (page: Page) => page.getByRole('complementary', { name: 'Change summary' })
const entry = (summary: Locator, label: string) => summary.getByRole('listitem', { name: label, exact: true })

/** A class's drawn shape: the node's own box is transparent, its shape is its first child. */
const shape = (map: Locator, label: string) =>
  map.getByRole('group', { name: label, exact: true }).locator(':scope > *').first()

test('a comparison sums up its changes beside the Map, per level and per Concept', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const summary = summaryOf(page)

  await expect(summary.getByRole('status')).toHaveText('2 breaking · 3 additive')
  const entries = summary.getByRole('list', { name: 'Changed Concepts' }).getByRole('listitem')
  // Most severe first: Stop and Trip each lost an attribute, HAS_TRIP only gained a description.
  await expect
    .poll(() => entries.evaluateAll((items) => items.map((i) => i.getAttribute('aria-label'))))
    .toEqual(['Stop', 'Trip', 'HAS_TRIP'])
  await expect(entry(summary, 'Stop')).toContainText('attribute wheelchairBoarding removed (breaking)')
  await expect(entry(summary, 'Stop')).toContainText('attribute wheelchair_boarding added (additive)')
  await expect(entry(summary, 'HAS_TRIP')).toContainText('description changed (additive)')

  // The Compare page has it too.
  await page.goto('/ui/kg/city-transit/versions/compare?id=2&id=3')
  await expect(summaryOf(page).getByRole('status')).toHaveText('2 breaking · 3 additive')
})

test('an entry focuses its Concept on the Map, and selecting on the Map finds its entry', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const map = ontologyMap(page)
  const summary = summaryOf(page)
  const faded = (label: string) => shape(map, label).evaluate((el: HTMLElement) => el.dataset.faded === 'true')
  await expect(shape(map, 'Agency')).toBeVisible()

  // Hovering previews the focus: Trip's neighbours stay, Agency fades, and nothing is selected.
  await entry(summary, 'Trip').hover()
  await expect.poll(() => faded('Agency')).toBe(true)
  expect(await faded('Route')).toBe(false)
  await expect(page.getByRole('complementary', { name: 'Details' })).toHaveCount(0)
  await page.mouse.move(0, 0)
  await expect.poll(() => faded('Agency')).toBe(false)

  // Clicking selects it.
  await entry(summary, 'Stop').getByRole('button').click()
  await expect(shape(map, 'Stop')).toHaveAttribute('data-selected', 'true')
  await expect(page.getByRole('complementary', { name: 'Details' })).toContainText('Stop')
  await expect(entry(summary, 'Stop').getByRole('button')).toHaveAttribute('aria-current', 'true')

  // Selecting on the Map highlights the entry, the relation's for a link.
  await map.getByRole('group', { name: 'Trip', exact: true }).click()
  await expect(entry(summary, 'Trip').getByRole('button')).toHaveAttribute('aria-current', 'true')
  await expect(entry(summary, 'Trip')).toBeInViewport()
  await expect(entry(summary, 'Stop').getByRole('button')).not.toHaveAttribute('aria-current')
  await map.getByRole('group', { name: '(Route)-[HAS_TRIP]->(Trip)', exact: true }).click()
  await expect(entry(summary, 'HAS_TRIP').getByRole('button')).toHaveAttribute('aria-current', 'true')
})

test('a comparison without changes says so', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/compare?id=3&id=3')

  await expect(summaryOf(page)).toContainText('No changes between the two versions.')
})
