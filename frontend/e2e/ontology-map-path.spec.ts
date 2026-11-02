import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

// A window tall enough for the Map to show all of this Ontology at the readable zoom.
test.use({ seed: 'ontology_map_path', viewport: { width: 1280, height: 1000 } })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const pathPanel = (page: Page) => page.getByRole('complementary', { name: 'Path' })

/** A class's node, or a link by its Pattern. */
const item = (map: Locator, name: string) => map.getByRole('group', { name, exact: true })
/** The drawn shape of a class's node, which carries its highlight state. */
const shape = (map: Locator, label: string) => item(map, label).locator('[data-class]')

/**
 * Selects the path from `from` to `to` as a user would: click one, shift-click the other.
 * The first click opens the Details panel, which narrows the Map, so `to` must still be in
 * view beside it. A class hidden under the panel is reached only by Playwright scrolling the
 * Map's clipped canvas, and that click can land on the bare pane, which clears the selection.
 */
async function selectPath(map: Locator, from: string, to: string) {
  await item(map, from).click()
  await expect(item(map, to)).toBeInViewport({ ratio: 1 })
  await item(map, to).click({ modifiers: ['Shift'] })
}

test('selecting two classes highlights the shortest path between them', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await selectPath(map, 'Customer', 'Product')

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

  // Address, on the Map's right, is selected first: the Details panel then covers it.
  await selectPath(map, 'Address', 'Ticket')

  // Customer inherits Party's LIVES_AT, so Party lights up along with the path.
  await expect(shape(map, 'Customer')).not.toHaveAttribute('data-faded')
  await expect(shape(map, 'Party')).not.toHaveAttribute('data-faded')
  await expect(shape(map, 'Product')).toHaveAttribute('data-faded')
  const panel = pathPanel(page)
  await expect(panel).toContainText('Address → Customer → Ticket')
  await expect(panel).toContainText('inherited from Party')
})

test('the Map says so when no path connects two classes', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  // Agent, on the Map's right, is selected first: the Details panel then covers it.
  await selectPath(map, 'Agent', 'Customer')

  await expect(pathPanel(page)).toContainText('No path connects Agent and Customer')
  await expect(shape(map, 'Ticket')).toHaveAttribute('data-faded')

  await page.keyboard.press('Escape')
  await expect(pathPanel(page)).toHaveCount(0)
})
