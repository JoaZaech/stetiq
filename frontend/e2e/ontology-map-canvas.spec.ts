import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_transit' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const changeKindKey = (page: Page) => page.getByRole('region', { name: 'Change kind' })

type Box = { x: number; y: number; width: number; height: number }

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height

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

test('the canvas keys only change kind, in one row by the zoom controls, over no class', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes')
  const map = ontologyMap(page)
  await expect(map.getByRole('group', { name: 'Trip', exact: true })).toBeVisible()
  const key = changeKindKey(page)

  await expect(key.getByRole('listitem')).toHaveText(['added', 'removed', 'modified', 'unchanged'])
  // Severity's key is the panel's headline counts, never the canvas.
  await expect(map.locator('[data-swatch]')).toHaveCount(0)
  await expect(map.getByText(/breaking|deprecating|additive|documentation-only/)).toHaveCount(0)

  // One row.
  const items = await key.getByRole('listitem').evaluateAll((els) => els.map((el) => el.getBoundingClientRect().top))
  expect(new Set(items.map(Math.round)).size).toBe(1)

  // At the bottom-left, beside the zoom controls and clear of them.
  const canvas = (await map.boundingBox())!
  const keyBox = (await key.boundingBox())!
  const controls = (await map.locator('.react-flow__controls').boundingBox())!
  expect(overlap(keyBox, controls)).toBe(false)
  expect(keyBox.x).toBeGreaterThanOrEqual(controls.x + controls.width)
  expect(keyBox.x).toBeLessThan(canvas.x + canvas.width / 2)
  expect(keyBox.y + keyBox.height).toBeGreaterThan(controls.y + controls.height - 30)

  // Over no class at the first view.
  for (const node of await map.locator('.react-flow__node').all()) {
    const box = await node.boundingBox()
    if (box) expect(overlap(keyBox, box), (await node.getAttribute('aria-label')) ?? undefined).toBe(false)
  }
})

test('the plain Map has no change-kind key', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/ontology')
  await expect(ontologyMap(page).getByRole('group', { name: 'Trip', exact: true })).toBeVisible()
  await expect(changeKindKey(page)).toHaveCount(0)
})
