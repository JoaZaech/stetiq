import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_path' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const pathPanel = (page: Page) => page.getByRole('complementary', { name: 'Path' })

/** A class's node, or a link by its Pattern. */
const item = (map: Locator, name: string) => map.getByRole('group', { name, exact: true })
/** The drawn shape of a class's node, which carries its highlight state. */
const shape = (map: Locator, label: string) => item(map, label).locator('[data-class]')

/**
 * Zoom out until the whole Map is in view: it opens at the readable zoom, at which this
 * Ontology's far classes lie outside the Map, too far to click.
 */
async function zoomOutToAll(map: Locator) {
  for (let i = 0; i < 2; i++) await map.getByRole('button', { name: 'Zoom Out' }).click()
}

test('selecting two classes highlights the shortest path between them', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await item(map, 'Customer').click()
  await item(map, 'Product').click({ modifiers: ['Shift'] })

  await expect(shape(map, 'Customer')).toHaveAttribute('data-selected')
  await expect(shape(map, 'Product')).toHaveAttribute('data-selected')
  await expect(shape(map, 'Ticket')).not.toHaveAttribute('data-faded')
  await expect(shape(map, 'Address')).toHaveAttribute('data-faded')
  const panel = pathPanel(page)
  await expect(panel).toContainText('Customer → Ticket → Product')
  await expect(panel).toContainText('2 steps')
})

test("a path through a superclass's Pattern is found", async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await zoomOutToAll(map)
  await item(map, 'Ticket').click()
  await item(map, 'Address').click({ modifiers: ['Shift'] })

  // Customer inherits Party's LIVES_AT, so Party lights up along with the path.
  await expect(shape(map, 'Customer')).not.toHaveAttribute('data-faded')
  await expect(shape(map, 'Party')).not.toHaveAttribute('data-faded')
  await expect(shape(map, 'Product')).toHaveAttribute('data-faded')
  const panel = pathPanel(page)
  await expect(panel).toContainText('Ticket → Customer → Address')
  await expect(panel).toContainText('inherited from Party')
})

test('the Map says so when no path connects two classes', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await zoomOutToAll(map)
  await item(map, 'Customer').click()
  await item(map, 'Agent').click({ modifiers: ['Shift'] })

  await expect(pathPanel(page)).toContainText('No path connects Customer and Agent')
  await expect(shape(map, 'Ticket')).toHaveAttribute('data-faded')

  await page.keyboard.press('Escape')
  await expect(pathPanel(page)).toHaveCount(0)
})
