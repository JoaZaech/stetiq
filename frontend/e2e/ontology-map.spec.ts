import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })

/** The `d` of a link's drawn path, the link named by its Pattern. */
const linkPath = (map: Locator, pattern: string) =>
  map.getByRole('group', { name: pattern, exact: true }).locator('path.react-flow__edge-path')

test('the Ontology tab opens on a Map of classes and the Patterns between them', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')

  await expect(page.getByRole('radio', { name: 'Map' })).toBeChecked()
  const map = ontologyMap(page)
  for (const label of ['Customer', 'Product', 'Ticket']) {
    await expect(map.getByRole('group', { name: label, exact: true })).toHaveText(label)
  }
  for (const pattern of [
    '(Customer)-[FOLLOWS]->(Ticket)',
    '(Customer)-[OPENED]->(Ticket)',
    '(Ticket)-[ABOUT]->(Product)',
    '(Ticket)-[DUPLICATES]->(Ticket)',
  ]) {
    await expect(map.getByRole('group', { name: pattern, exact: true })).toBeVisible()
  }
  for (const relation of ['ABOUT', 'DUPLICATES', 'FOLLOWS', 'OPENED']) {
    await expect(map.getByText(relation, { exact: true })).toBeVisible()
  }

  // The two relations between Customer and Ticket are two separate links.
  const opened = await linkPath(map, '(Customer)-[OPENED]->(Ticket)').getAttribute('d')
  const follows = await linkPath(map, '(Customer)-[FOLLOWS]->(Ticket)').getAttribute('d')
  expect(opened).not.toEqual(follows)
  // The self-loop is an arc that leaves and returns to Ticket, not a zero-length line.
  const loop = await linkPath(map, '(Ticket)-[DUPLICATES]->(Ticket)').boundingBox()
  expect(loop?.width).toBeGreaterThan(10)
  expect(loop?.height).toBeGreaterThan(10)
})

test('the Table / Map toggle switches views and round-trips through the URL', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  await expect(ontologyMap(page)).toBeVisible()

  await page.getByRole('radio', { name: 'Table' }).click()

  await expect(page).toHaveURL('/ui/kg/support/versions/1/ontology?view=table')
  await expect(page.getByRole('table', { name: 'Classes' })).toBeVisible()
  await expect(ontologyMap(page)).toHaveCount(0)

  // The URL alone reopens the Table, and the search stays when switching back to the Map.
  await page.reload()
  await expect(page.getByRole('radio', { name: 'Table' })).toBeChecked()
  await page.getByRole('searchbox', { name: 'Search Concepts' }).fill('ticket')
  await page.getByRole('radio', { name: 'Map' }).click()

  await expect(page).toHaveURL('/ui/kg/support/versions/1/ontology?q=ticket')
  await expect(ontologyMap(page)).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('table', { name: 'Classes' })).toBeVisible()
})

test('the Map pans and zooms', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)
  const viewport = map.locator('.react-flow__viewport')
  await expect(map.getByRole('group', { name: 'Ticket', exact: true })).toBeVisible()
  const transform = () => viewport.evaluate((el) => getComputedStyle(el).transform)

  const start = await transform()
  await map.getByRole('button', { name: 'Zoom In' }).click()
  await expect.poll(transform).not.toEqual(start)

  const zoomed = await transform()
  const box = (await map.boundingBox())!
  await page.mouse.move(box.x + 20, box.y + 20)
  await page.mouse.down()
  await page.mouse.move(box.x + 120, box.y + 80, { steps: 5 })
  await page.mouse.up()
  await expect.poll(transform).not.toEqual(zoomed)
})

test('the Map is drawn in the colours of the current theme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)
  const customer = map.getByRole('group', { name: 'Customer', exact: true })
  await expect(customer).toBeVisible()
  // Lightness, 0 (black) to 1 (white), of an element's background or text: the theme's
  // `oklch()` lightness, or the relative luminance of an `rgb()` colour.
  const lightness = (locator: Locator, property: 'backgroundColor' | 'color') =>
    locator.evaluate((el, p) => {
      // The node's own box is transparent; its drawn shape is its first child.
      const colour = getComputedStyle(el.firstElementChild ?? el)[p]
      const [a, b, c] = colour.match(/[\d.]+/g)!.map(Number)
      return colour.startsWith('oklch') ? a : (0.2126 * a + 0.7152 * b + 0.0722 * c) / 255
    }, property)

  await expect.poll(() => lightness(customer, 'backgroundColor')).toBeGreaterThan(0.6)
  await expect.poll(() => lightness(customer, 'color')).toBeLessThan(0.4)

  await page.emulateMedia({ colorScheme: 'dark' })

  await expect.poll(() => lightness(customer, 'backgroundColor')).toBeLessThan(0.4)
  await expect.poll(() => lightness(customer, 'color')).toBeGreaterThan(0.6)
})
