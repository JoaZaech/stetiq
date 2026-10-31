import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })

/** A link's relation label, by its relation. */
const label = (map: Locator, relation: string) => map.locator('[data-link-label]', { hasText: relation })

/** The Map's zoom: the scale of its viewport's transform. */
const zoom = (map: Locator) =>
  map
    .locator('.react-flow__viewport')
    .evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).a)

/** Click the Map's zoom button until `done` holds of its zoom. */
async function zoomUntil(map: Locator, button: 'Zoom In' | 'Zoom Out', done: (zoom: number) => boolean) {
  for (let i = 0; i < 20 && !done(await zoom(map)); i++) {
    const before = await zoom(map)
    await map.getByRole('button', { name: button }).click()
    await expect.poll(() => zoom(map)).not.toEqual(before)
  }
  expect(done(await zoom(map))).toBe(true)
}

/** The least zoom at which link labels are readable (`READABLE_ZOOM`). */
const READABLE_ZOOM = 0.7

/** The least zoom the Map's first view frames at (`FIRST_VIEW_MIN_ZOOM`). */
const FIRST_VIEW_MIN_ZOOM = 0.85

/** The Map's least zoom (`OntologyMap`'s `minZoom`), which Fit view stops at. */
const MAP_MIN_ZOOM = 0.2

test.describe('on the Ontology tab', () => {
  test.use({ seed: 'ontology_map' })

  test('link labels are drawn on top of nodes and links, on a solid background in either theme', async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: 'light' })
    await page.goto('/ui/kg/support/versions/1/ontology')
    const map = ontologyMap(page)
    const relations = ['ABOUT', 'DUPLICATES', 'FILED', 'FOLLOWS', 'OPENED']
    for (const relation of relations) await expect(label(map, relation)).toBeVisible()

    // Nothing is drawn over a label: what is on top at its centre is the label itself.
    const onTop = (locator: Locator) =>
      locator.evaluate((el) => {
        const { x, y, width, height } = el.getBoundingClientRect()
        // Labels let clicks through to the link; hit-test them as if they did not.
        el.style.pointerEvents = 'auto'
        const hit = document.elementFromPoint(x + width / 2, y + height / 2)
        el.style.pointerEvents = ''
        return hit !== null && el.contains(hit)
      })
    // A label's background: whether it is opaque (an alpha of 1 and no opacity), and its
    // lightness, 0 (black) to 1 (white): the theme's `oklch()` lightness, or the relative
    // luminance of an `rgb()` colour.
    const background = (locator: Locator) =>
      locator.evaluate((el) => {
        const style = getComputedStyle(el)
        const colour = style.backgroundColor
        const [a, b, c, alpha = 1] = colour.match(/[\d.]+/g)!.map(Number)
        return {
          opaque: alpha === 1 && Number(style.opacity) === 1,
          lightness: colour.startsWith('oklch') ? a : (0.2126 * a + 0.7152 * b + 0.0722 * c) / 255,
        }
      })

    // Even with a node moved right over it.
    const product = map.getByRole('group', { name: 'Product', exact: true })
    await product.evaluate(
      (node, target) => {
        const zoom = new DOMMatrixReadOnly(getComputedStyle(node.closest('.react-flow__viewport')!).transform).a
        const from = node.getBoundingClientRect()
        const to = target!.getBoundingClientRect()
        const dx = to.x + to.width / 2 - (from.x + from.width / 2)
        const dy = to.y + to.height / 2 - (from.y + from.height / 2)
        node.style.translate = `${dx / zoom}px ${dy / zoom}px`
      },
      await label(map, 'OPENED').elementHandle(),
    )
    expect(await onTop(label(map, 'OPENED'))).toBe(true)
    await product.evaluate((node) => (node.style.translate = ''))

    for (const relation of relations) {
      expect(await onTop(label(map, relation)), relation).toBe(true)
      expect(await background(label(map, relation))).toEqual({ opaque: true, lightness: expect.any(Number) })
    }
    expect((await background(label(map, 'OPENED'))).lightness).toBeGreaterThan(0.6)

    await page.emulateMedia({ colorScheme: 'dark' })

    await expect.poll(async () => (await background(label(map, 'OPENED'))).lightness).toBeLessThan(0.4)
    for (const relation of relations) {
      expect(await background(label(map, relation))).toEqual({ opaque: true, lightness: expect.any(Number) })
    }
  })

  test('zoomed out, only the selection’s link labels show; zoomed in, all of them', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/1/ontology')
    const map = ontologyMap(page)
    await expect(label(map, 'OPENED')).toBeVisible()

    await zoomUntil(map, 'Zoom Out', (z) => z < READABLE_ZOOM)

    for (const relation of ['ABOUT', 'DUPLICATES', 'FILED', 'FOLLOWS', 'OPENED']) {
      await expect(label(map, relation)).toBeHidden()
    }

    // Selecting Customer brings back the labels of its links only.
    await map.getByRole('group', { name: 'Customer', exact: true }).click()
    for (const relation of ['FILED', 'FOLLOWS', 'OPENED']) await expect(label(map, relation)).toBeVisible()
    for (const relation of ['ABOUT', 'DUPLICATES']) await expect(label(map, relation)).toBeHidden()

    await page.keyboard.press('Escape')
    await expect(label(map, 'OPENED')).toBeHidden()

    await zoomUntil(map, 'Zoom In', (z) => z >= READABLE_ZOOM)

    for (const relation of ['ABOUT', 'DUPLICATES', 'FILED', 'FOLLOWS', 'OPENED']) {
      await expect(label(map, relation)).toBeVisible()
    }
  })

  test('zoomed out, a comparison keeps the labels of changed links', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/2/changes')
    const map = ontologyMap(page)
    await expect(label(map, 'IN_QUEUE')).toBeVisible()

    await zoomUntil(map, 'Zoom Out', (z) => z < READABLE_ZOOM)

    // IN_QUEUE was added and ABOUT removed; OPENED and DUPLICATES did not change.
    for (const relation of ['ABOUT', 'IN_QUEUE']) await expect(label(map, relation)).toBeVisible()
    for (const relation of ['DUPLICATES', 'OPENED']) await expect(label(map, relation)).toBeHidden()
  })
})

test.describe('an Ontology bigger than the Map', () => {
  test.use({ seed: 'ontology_map_large' })

  test('opens at the zoom class names can be read at, and Fit view zooms out past that to frame all of it', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/1/ontology')
    const map = ontologyMap(page)
    await expect(map.getByRole('group', { name: 'Class00', exact: true })).toBeAttached()

    await expect.poll(() => zoom(map)).toBeCloseTo(FIRST_VIEW_MIN_ZOOM, 2)
    // Too big to fit: some classes lie outside the Map, to be panned to.
    const outside = await map.getByRole('group', { name: /^Class\d\d$/ }).evaluateAll((nodes, box) => {
      const { left, right, top, bottom } = box as DOMRect
      return nodes.some((n) => {
        const r = n.getBoundingClientRect()
        return r.right < left || r.left > right || r.bottom < top || r.top > bottom
      })
    }, await map.evaluate((el) => el.getBoundingClientRect().toJSON()))
    expect(outside).toBe(true)

    // Fit view zooms out past the first view's floor to frame the whole Map, as far as the
    // Map's least zoom; this one is too big to fit even there.
    await map.getByRole('button', { name: 'Fit View' }).click()
    await expect.poll(() => zoom(map)).toBeCloseTo(MAP_MIN_ZOOM, 2)
  })
})
