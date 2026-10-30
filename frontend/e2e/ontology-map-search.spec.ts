import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_search' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const results = (page: Page) => page.getByRole('complementary', { name: 'Search results' })
const details = (page: Page) => page.getByRole('complementary', { name: 'Details' })

const item = (map: Locator, name: string) => map.getByRole('group', { name, exact: true })
const shape = (map: Locator, label: string) => item(map, label).locator('[data-class]')

/** How far `label`'s node sits from the middle of the Map's canvas, in pixels. */
async function offCentre(page: Page, label: string) {
  const canvas = await ontologyMap(page).boundingBox()
  const node = await item(ontologyMap(page), label).boundingBox()
  if (!canvas || !node) return Infinity
  return Math.hypot(
    node.x + node.width / 2 - (canvas.x + canvas.width / 2),
    node.y + node.height / 2 - (canvas.y + canvas.height / 2),
  )
}

test('the search lists name matches, then other matches with their reasons, and highlights only names', async ({
  page,
}) => {
  await page.goto('/ui/kg/retail/versions/1/ontology')
  const map = ontologyMap(page)

  await page.getByRole('searchbox', { name: 'Search Concepts' }).fill('Warehouse')

  await expect(page).toHaveURL('/ui/kg/retail/versions/1/ontology?q=Warehouse')
  const list = results(page)
  await expect(list.getByRole('list', { name: 'Name matches' }).getByRole('listitem')).toHaveText([/^Warehouse\s*class$/])
  await expect(list.getByRole('list', { name: 'Other matches' }).getByRole('listitem')).toHaveText([
    /^Bin\s*class\s*description mentions 'warehouse'; attribute warehouse$/,
    /^SHIPPED_FROM\s*relation\s*description mentions 'warehouse'$/,
  ])

  await expect(shape(map, 'Warehouse')).toHaveAttribute('data-match')
  await expect(shape(map, 'Bin')).not.toHaveAttribute('data-match')
  await expect(shape(map, 'Bin')).toHaveAttribute('data-faded')

  // The Table keeps full-text filtering: Bin is there by its description and attribute.
  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(page.getByRole('table', { name: 'Classes' }).getByRole('row')).toHaveText([/Class/, /^Bin/, /^Warehouse/])
  await expect(page.getByRole('table', { name: 'Attributes' }).getByRole('row')).toHaveText([/Attribute/, /^Bin · class/, /^warehouse/])
})

test('picking a result selects it and centres the Map on it, by mouse or keyboard', async ({ page }) => {
  await page.goto('/ui/kg/retail/versions/1/ontology?q=warehouse')
  const map = ontologyMap(page)

  await results(page).getByRole('button', { name: /^Bin/ }).click()

  await expect(shape(map, 'Bin')).toHaveAttribute('data-selected')
  await expect(details(page).getByRole('heading', { name: 'Bin' })).toBeVisible()
  await expect.poll(() => offCentre(page, 'Bin')).toBeLessThan(4)

  // A relation's result selects its link.
  await results(page).getByRole('button', { name: /^SHIPPED_FROM/ }).focus()
  await page.keyboard.press('Enter')
  await expect(details(page).getByRole('heading', { name: 'SHIPPED_FROM' })).toBeVisible()

  // Arrow keys move between results; Enter picks.
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('ArrowUp')
  await expect(results(page).getByRole('button', { name: /^Warehouse/ })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(shape(map, 'Warehouse')).toHaveAttribute('data-selected')
  await expect.poll(() => offCentre(page, 'Warehouse')).toBeLessThan(4)
})
