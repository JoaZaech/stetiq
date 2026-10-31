import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })

/** Whether `filter` sits in the header row beside the Table / Map toggle, off the canvas. */
async function inHeaderRow(page: Page, filter: Locator) {
  const toggle = await page.getByRole('radio', { name: 'Map' }).boundingBox()
  const box = await filter.boundingBox()
  const canvas = await ontologyMap(page).boundingBox()
  if (!toggle || !box || !canvas) return false
  const middle = box.y + box.height / 2
  return middle > toggle.y && middle < toggle.y + toggle.height && box.y + box.height <= canvas.y
}

// Every Map surface: the Ontology tab, the Changes tab and the Compare page.
test.describe('filters', () => {
  test.use({ seed: 'ontology_map' })

  for (const [surface, url] of [
    ['Ontology tab', '/ui/kg/support/versions/1/ontology'],
    ['Changes tab', '/ui/kg/support/versions/2/changes'],
    ['Compare page', '/ui/kg/support/versions/compare?id=1&id=3'],
  ] as const) {
    test(`the ${surface}'s Map filters sit in the header row and still filter the Map`, async ({ page }) => {
      await page.goto(url)
      const map = ontologyMap(page)
      const group = (name: string) => map.getByRole('group', { name, exact: true })
      await expect(group('LegacyTicket')).toBeVisible()

      for (const name of ['Hide deprecated', 'Hide subclass links']) {
        await expect(map.getByRole('switch', { name })).toHaveCount(0)
        await expect.poll(() => inHeaderRow(page, page.getByRole('switch', { name }))).toBe(true)
      }

      await page.getByRole('switch', { name: 'Hide deprecated' }).click()
      await expect(group('LegacyTicket')).toHaveCount(0)
      await page.getByRole('switch', { name: 'Hide subclass links' }).click()
      await expect(group('Customer -> Party')).toHaveCount(0)
    })
  }
})
