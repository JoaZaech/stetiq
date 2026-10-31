import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_transit' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
/** Every panel the Map can show beside it. */
const panels = (page: Page) =>
  page.getByRole('complementary', { name: /^(Change summary|Details|Path|Search results|Changes collapsed)$/ })
const panel = (page: Page, name: string) => page.getByRole('complementary', { name, exact: true })
const entry = (summary: Locator, label: string) => summary.getByRole('listitem', { name: label, exact: true })
const item = (map: Locator, name: string) => map.getByRole('group', { name, exact: true })

/** Whether the one panel beside the Map sits on its right, flush with the canvas. */
async function onlyPanelOnRight(page: Page) {
  if ((await panels(page).count()) !== 1) return false
  const canvas = await ontologyMap(page).boundingBox()
  const side = await panels(page).boundingBox()
  return canvas !== null && side !== null && Math.abs(side.x - (canvas.x + canvas.width)) < 2
}

test('one panel on the right goes from the change summary to details and back to the entry', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const summary = panel(page, 'Change summary')
  await expect(summary.getByRole('status')).toHaveText('2 breaking · 2 additive · 1 documentation-only')
  await expect.poll(() => onlyPanelOnRight(page)).toBe(true)

  // An entry opens its Concept's details in the same panel.
  await entry(summary, 'Stop').getByRole('button').click()
  const details = panel(page, 'Details')
  await expect(details.getByRole('heading', { name: 'Stop' })).toBeVisible()
  await expect.poll(() => onlyPanelOnRight(page)).toBe(true)

  // Back to the summary, at Stop's entry.
  await details.getByRole('button', { name: 'All changes' }).click()
  await expect(entry(summary, 'Stop').getByRole('button')).toHaveAttribute('aria-current', 'true')
  await expect(entry(summary, 'Stop')).toBeInViewport()

  // A documentation-only link selected on the Map returns to its entry, its section opened.
  await item(ontologyMap(page), '(Route)-[HAS_TRIP]->(Trip)').click()
  await expect(details.getByRole('heading', { name: 'HAS_TRIP' })).toBeVisible()
  await details.getByRole('button', { name: 'All changes' }).click()
  await expect(summary.getByRole('button', { name: 'Documentation-only 1' })).toHaveAttribute(
    'aria-expanded',
    'true',
  )
  await expect(entry(summary, 'HAS_TRIP')).toBeInViewport()

  // The Compare page has the same one panel.
  await page.goto('/ui/kg/city-transit/versions/compare?id=2&id=3')
  await expect(panel(page, 'Change summary')).toBeVisible()
  await expect.poll(() => onlyPanelOnRight(page)).toBe(true)
})

test('a shortest path opens in the same panel, back to the summary', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const map = ontologyMap(page)

  // Two changed classes, both in the first view, which frames the changes.
  await item(map, 'Stop').click()
  await item(map, 'Trip').click({ modifiers: ['Shift'] })

  const path = panel(page, 'Path')
  await expect(path).toContainText('Stop → Trip')
  await expect.poll(() => onlyPanelOnRight(page)).toBe(true)
  await path.getByRole('button', { name: 'All changes' }).click()
  await expect(panel(page, 'Change summary')).toBeVisible()
})

test('search results open in the same panel, and a picked result goes back to them', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/ontology?q=trip')
  const results = panel(page, 'Search results')
  await expect(results.getByRole('button', { name: /^Trip/ })).toBeVisible()
  await expect.poll(() => onlyPanelOnRight(page)).toBe(true)

  await results.getByRole('button', { name: /^Trip/ }).click()
  const details = panel(page, 'Details')
  await expect(details.getByRole('heading', { name: 'Trip' })).toBeVisible()
  await expect.poll(() => onlyPanelOnRight(page)).toBe(true)

  await details.getByRole('button', { name: 'Results' }).click()
  await expect(results.getByRole('button', { name: /^Trip/ })).toBeVisible()
  await expect(details).toHaveCount(0)
})

test('the panel collapses to a rail of the headline counts, each with its severity swatch', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const map = ontologyMap(page)
  const counts = panel(page, 'Change summary').getByRole('status')
  // The counts are the severity key: a swatch each, documentation-only its neutral dot.
  await expect(counts.locator('[data-swatch]')).toHaveCount(2)
  await expect(counts.locator('[data-swatch="breaking"]')).toHaveCount(1)
  await expect(counts.locator('[data-swatch="additive"]')).toHaveCount(1)
  await expect(counts.locator('[data-cosmetic-dot]')).toHaveCount(1)
  const width = (await map.boundingBox())!.width

  await page.getByRole('button', { name: 'Collapse panel' }).click()
  const rail = panel(page, 'Changes collapsed')
  await expect(rail.getByRole('status')).toHaveText(/2\s*breaking.*2\s*additive.*1\s*documentation-only/)
  await expect(rail.locator('[data-swatch], [data-cosmetic-dot]')).toHaveCount(3)
  await expect.poll(async () => (await map.boundingBox())!.width).toBeGreaterThan(width + 200)

  await rail.getByRole('button', { name: 'Expand panel' }).click()
  await expect(panel(page, 'Change summary')).toBeVisible()
})

test('a collapsed panel opens again for a selection on the Map, or a shortest path', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const map = ontologyMap(page)
  await page.getByRole('button', { name: 'Collapse panel' }).click()
  await expect(panel(page, 'Changes collapsed')).toBeVisible()

  // A class clicked on the canvas shows its details, not the rail.
  await item(map, 'Stop').click()
  await expect(panel(page, 'Details').getByRole('heading', { name: 'Stop' })).toBeVisible()
  await expect(panel(page, 'Changes collapsed')).toHaveCount(0)

  // Collapsed again, a shift-click shows the shortest path.
  await page.getByRole('button', { name: 'Collapse panel' }).click()
  await expect(panel(page, 'Changes collapsed')).toBeVisible()
  await item(map, 'Trip').click({ modifiers: ['Shift'] })
  await expect(panel(page, 'Path')).toContainText('Stop → Trip')
  await expect(panel(page, 'Changes collapsed')).toHaveCount(0)
})
