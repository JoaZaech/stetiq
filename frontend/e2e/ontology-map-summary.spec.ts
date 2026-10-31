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

  await expect(summary.getByRole('status')).toHaveText('2 breaking · 2 additive · 1 documentation-only')
  const entries = summary.getByRole('list', { name: 'Changed Concepts' }).getByRole('listitem')
  // Most severe first: Stop and Trip each lost an attribute.
  await expect
    .poll(() => entries.evaluateAll((items) => items.map((i) => i.getAttribute('aria-label'))))
    .toEqual(['Stop', 'Trip'])
  await expect(entry(summary, 'Stop')).toContainText('attribute wheelchairBoarding removed (breaking)')
  await expect(entry(summary, 'Stop')).toContainText('attribute wheelchair_boarding added (additive)')

  // The Compare page has it too.
  await page.goto('/ui/kg/city-transit/versions/compare?id=2&id=3')
  await expect(summaryOf(page).getByRole('status')).toHaveText('2 breaking · 2 additive · 1 documentation-only')
})

test('documentation-only changes collapse to one line in the summary, and to a neutral dot on the Map', async ({
  page,
}) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const map = ontologyMap(page)
  const summary = summaryOf(page)

  // Only HAS_TRIP's description changed: one collapsed line, which expands to its entry.
  const line = summary.getByRole('button', { name: '1 documentation-only change' })
  await expect(line).toHaveAttribute('aria-expanded', 'false')
  await expect(entry(summary, 'HAS_TRIP')).toBeHidden()
  await line.click()
  await expect(entry(summary, 'HAS_TRIP')).toContainText('description changed (documentation-only)')

  // On the Map its link has no severity colour, only a dot: the v2 → v3 links are not all green.
  const hasTrip = map
    .getByRole('group', { name: '(Route)-[HAS_TRIP]->(Trip)', exact: true })
    .locator('path.react-flow__edge-path')
  await expect
    .poll(() => hasTrip.evaluate((el: SVGElement) => [el.dataset.change, el.dataset.severity ?? null]))
    .toEqual(['documentation-only', null])
  const severities = await map
    .locator('path.react-flow__edge-path')
    .evaluateAll((paths) => paths.map((p) => (p as SVGElement).dataset.severity ?? null))
  expect(severities.length).toBeGreaterThan(0)
  expect(severities.every((s) => s === null)).toBe(true)
  // One dot among the link labels: HAS_TRIP's (the legend has its own).
  await expect(map.locator('[data-link-label] [data-documentation-dot]')).toHaveCount(1)
  await expect(map.locator('[data-link-label]', { hasText: 'HAS_TRIP' }).locator('[data-documentation-dot]')).toHaveCount(1)
})

test('a documentation-only change shows its description before and after, the changed words marked', async ({
  page,
}) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const summary = summaryOf(page)

  // Its entry previews the new description.
  await summary.getByRole('button', { name: '1 documentation-only change' }).click()
  await expect(entry(summary, 'HAS_TRIP')).toContainText('The scheduled trips of a route')

  // Selected on the Map, its details show both descriptions, removed and added words marked.
  await ontologyMap(page).getByRole('group', { name: '(Route)-[HAS_TRIP]->(Trip)', exact: true }).click()
  const details = page.getByRole('complementary', { name: 'Details' })
  const before = details.getByRole('group', { name: 'Before' })
  const after = details.getByRole('group', { name: 'After' })
  await expect(before).toHaveText('The trips run on a route')
  await expect(after).toHaveText('The scheduled trips of a route')
  await expect(before.locator('del')).toHaveText(['run on'])
  await expect(before.locator('ins')).toHaveCount(0)
  await expect(after.locator('ins')).toHaveText(['scheduled', 'of'])
  await expect(after.locator('del')).toHaveCount(0)
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

  // Clicking selects it, its details in place of the summary.
  const details = page.getByRole('complementary', { name: 'Details' })
  const back = details.getByRole('button', { name: 'All changes' })
  await entry(summary, 'Stop').getByRole('button').click()
  await expect(shape(map, 'Stop')).toHaveAttribute('data-selected', 'true')
  await expect(details).toContainText('Stop')
  await back.click()
  await expect(entry(summary, 'Stop').getByRole('button')).toHaveAttribute('aria-current', 'true')

  // Selected on the Map, the summary returns to its entry, the relation's for a link.
  await map.getByRole('group', { name: 'Trip', exact: true }).click()
  await back.click()
  await expect(entry(summary, 'Trip').getByRole('button')).toHaveAttribute('aria-current', 'true')
  await expect(entry(summary, 'Trip')).toBeInViewport()
  await expect(entry(summary, 'Stop').getByRole('button')).not.toHaveAttribute('aria-current')
  await map.getByRole('group', { name: '(Route)-[HAS_TRIP]->(Trip)', exact: true }).click()
  await back.click()
  await expect(entry(summary, 'HAS_TRIP').getByRole('button')).toHaveAttribute('aria-current', 'true')
})

test('a comparison without changes says so', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/compare?id=3&id=3')

  await expect(summaryOf(page)).toContainText('No changes between the two versions.')
})

test.describe('with a filter hiding the first changed Pattern of a relation', () => {
  test.use({ seed: 'ontology_map_hidden_pattern' })

  test('a relation picked in the summary or on the Map selects the same link', async ({ page }) => {
    // OPENED gained two Patterns; the first, to the deprecated LegacyTicket, is hidden.
    await page.goto('/ui/kg/support/versions/2/changes?select=relation:OPENED')
    const details = page.getByRole('complementary', { name: 'Details' })
    await expect(details).toContainText('(Agent)-[OPENED]->(LegacyTicket)')
    // By keyboard: with the details open, the legend overlaps the filters.
    await page.getByRole('switch', { name: 'Hide deprecated' }).focus()
    await page.keyboard.press('Space')

    // Selected on the Map, the relation is its first changed link still shown.
    await expect(details).toContainText('(Agent)-[OPENED]->(Ticket)')

    // Picked in the summary, it is the same link.
    await page.keyboard.press('Escape')
    await expect(details).toHaveCount(0)
    await entry(summaryOf(page), 'OPENED').getByRole('button').click()
    await expect(details).toContainText('(Agent)-[OPENED]->(Ticket)')
    await details.getByRole('button', { name: 'All changes' }).click()
    await expect(entry(summaryOf(page), 'OPENED').getByRole('button')).toHaveAttribute('aria-current', 'true')
  })
})
