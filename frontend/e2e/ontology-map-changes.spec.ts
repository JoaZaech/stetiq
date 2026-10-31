import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })

/** A class's drawn shape: the node's own box is transparent, its shape is its first child. */
const shape = (map: Locator, label: string) =>
  map.getByRole('group', { name: label, exact: true }).locator(':scope > *').first()

const linkPath = (map: Locator, pattern: string) =>
  map.getByRole('group', { name: pattern, exact: true }).locator('path.react-flow__edge-path')

test('the Changes tab opens on the two versions superimposed on a Map', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/2/changes')
  await expect(page.getByRole('radio', { name: 'Map' })).toBeChecked()
  await expect(page.getByText('Changes from v1')).toBeVisible()
  const map = ontologyMap(page)
  const change = (label: string) =>
    shape(map, label).evaluate((el: HTMLElement) => [el.dataset.change, el.dataset.severity ?? null])
  await expect.poll(() => change('Queue')).toEqual(['added', 'additive'])
  // Removed: still drawn, as a ghost where it used to be.
  await expect.poll(() => change('Product')).toEqual(['removed', 'breaking'])
  // A required attribute added to Ticket is a breaking change to it.
  await expect.poll(() => change('Ticket')).toEqual(['modified', 'breaking'])
  await expect.poll(() => change('Customer')).toEqual(['unchanged', null])

  const dashed = (path: Locator) => path.evaluate((el) => getComputedStyle(el).strokeDasharray !== 'none')
  expect(await dashed(linkPath(map, '(Ticket)-[ABOUT]->(Product)'))).toBe(true)
  expect(await dashed(linkPath(map, '(Ticket)-[IN_QUEUE]->(Queue)'))).toBe(false)
  expect(await dashed(linkPath(map, '(Customer)-[OPENED]->(Ticket)'))).toBe(false)

  // The Table is the Diff's own list, at `?view=table`; the URL alone reopens it.
  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(page).toHaveURL('/ui/kg/support/versions/2/changes?view=table')
  await expect(page.getByRole('region', { name: 'Ontology Diff' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('region', { name: 'Ontology Diff' })).toBeVisible()
  await expect(ontologyMap(page)).toHaveCount(0)
})

test("selecting a changed class shows the Diff's change detail", async ({ page }) => {
  await page.goto('/ui/kg/support/versions/2/changes')
  const map = ontologyMap(page)

  await map.getByRole('group', { name: 'Ticket', exact: true }).click()

  const details = page.getByRole('complementary', { name: 'Details' })
  const changes = details.getByRole('list', { name: 'Changes' })
  await expect(changes).toContainText('breaking')
  await expect(changes).toContainText('required property Ticket.priority added')
  // The details are the current version's: the new attribute is listed.
  await expect(details.getByRole('table', { name: 'Attributes' })).toContainText('priority')

  await map.getByRole('group', { name: 'Customer', exact: true }).click()
  await expect(details).toContainText('No attributes.')
  await expect(details).toContainText('No changes.')
})

test('severity is drawn in the Diff colours, legible in both themes', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/ui/kg/support/versions/2/changes')
  const map = ontologyMap(page)
  const product = shape(map, 'Product')
  await expect(product).toBeVisible()

  /** The `oklch()` lightness of a colour, 0 (black) to 1 (white). */
  const lightness = (colour: string) => Number(/oklch\(([\d.]+)/.exec(colour)![1])
  const colours = () =>
    product.evaluate((el) => {
      // The theme's breaking colour, resolved as the browser computes it.
      const probe = document.body.appendChild(document.createElement('span'))
      probe.style.color = 'var(--diff-breaking)'
      const breaking = getComputedStyle(probe).color
      probe.remove()
      return {
        border: getComputedStyle(el).borderTopColor,
        breaking,
        background: getComputedStyle(document.body).backgroundColor,
      }
    })
  const expectLegible = async () => {
    const { border, breaking, background } = await colours()
    // The removed class's outline is the breaking colour, set well apart from the page.
    expect(border).toEqual(breaking)
    expect(Math.abs(lightness(border) - lightness(background))).toBeGreaterThan(0.3)
  }

  await expectLegible()
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect.poll(async () => lightness((await colours()).background)).toBeLessThan(0.4)
  await expectLegible()
})

test('v1 still has nothing to compare, even on the Map', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/changes')

  await expect(
    page.getByText('v1 is the first Ontology Version: there is nothing to compare it with.'),
  ).toBeVisible()
  await expect(ontologyMap(page)).toHaveCount(0)
})

test.describe('with an attribute renamed and another made required', () => {
  test.use({ seed: 'ontology_map_attributes' })

  test('a changed class lists just its changed attributes, diff-style, in their severity', async ({ page }) => {
    await page.goto('/ui/kg/transit/versions/2/changes')
    const map = ontologyMap(page)
    const stop = map.getByRole('group', { name: 'Stop', exact: true })
    const attributes = stop.getByRole('list', { name: 'Changed attributes' }).getByRole('listitem')

    // The rename is a removal and an addition; the unchanged `code` stays hidden.
    await expect(attributes).toHaveText(['~ name now required', '− wheelchairBoarding', '+ wheelchair_boarding'])
    const severities = await attributes.evaluateAll((items) => items.map((i) => (i as HTMLElement).dataset.severity))
    expect(severities).toEqual(['breaking', 'breaking', 'additive'])
    // The unchanged Route lists none.
    await expect(map.getByRole('group', { name: 'Route', exact: true }).getByRole('list')).toHaveCount(0)

    // The expanded Stop keeps clear of Route.
    const [s, r] = [await stop.boundingBox(), await map.getByRole('group', { name: 'Route', exact: true }).boundingBox()]
    const overlap = s!.x < r!.x + r!.width && r!.x < s!.x + s!.width && s!.y < r!.y + r!.height && r!.y < s!.y + s!.height
    expect(overlap).toBe(false)
  })

  test('the plain Map lists no attributes on a class', async ({ page }) => {
    await page.goto('/ui/kg/transit/versions/2/ontology')
    const stop = ontologyMap(page).getByRole('group', { name: 'Stop', exact: true })

    await expect(stop).toBeVisible()
    await expect(stop.getByRole('list')).toHaveCount(0)
  })
})

test.describe('with a Pattern added beside another of its relation', () => {
  test.use({ seed: 'ontology_map_patterns' })

  // The Map reads which Pattern an endpoint change names from the Diff's wording
  // (ontology/diff.py `_diff_patterns`): this fails if the server words it differently.
  test("the Diff's endpoint change marks only the Pattern it names", async ({ page }) => {
    await page.goto('/ui/kg/support/versions/2/changes')
    const map = ontologyMap(page)
    const change = (pattern: string) =>
      linkPath(map, pattern).evaluate((el: SVGElement) => [el.dataset.change, el.dataset.severity ?? null])

    await expect.poll(() => change('(Agent)-[OPENED]->(Ticket)')).toEqual(['added', 'additive'])
    await expect.poll(() => change('(Customer)-[OPENED]->(Ticket)')).toEqual(['unchanged', null])
  })
})

test.describe('city transit, v2 → v3', () => {
  test.use({ seed: 'ontology_map_transit' })

  /** The Map's zoom: the scale of its viewport's transform. */
  const zoom = (map: Locator) =>
    map.locator('.react-flow__viewport').evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).a)

  test('opens on the changes, at a zoom whose class names can be read', async ({ page }) => {
    await page.goto('/ui/kg/city-transit/versions/3/changes')
    const map = ontologyMap(page)

    // Trip and Stop broke, and HAS_TRIP from Route is documentation-only.
    for (const label of ['Route', 'Stop', 'Trip']) await expect(shape(map, label)).toBeInViewport()
    await expect.poll(() => zoom(map)).toBeGreaterThanOrEqual(0.85)
    // Framed on them: centred on their bounds, not on the whole Map's.
    const centre = (box: { x: number; y: number; width: number; height: number }) => ({
      x: box.x + box.width / 2,
      y: box.y + box.height / 2,
    })
    const boxes = await Promise.all(['Route', 'Stop', 'Trip'].map(async (l) => (await shape(map, l).boundingBox())!))
    const [left, top] = [Math.min(...boxes.map((b) => b.x)), Math.min(...boxes.map((b) => b.y))]
    const right = Math.max(...boxes.map((b) => b.x + b.width))
    const bottom = Math.max(...boxes.map((b) => b.y + b.height))
    const changes = centre({ x: left, y: top, width: right - left, height: bottom - top })
    const pane = centre((await map.locator('.react-flow__renderer').boundingBox())!)
    expect(Math.abs(changes.x - pane.x)).toBeLessThan(8)
    expect(Math.abs(changes.y - pane.y)).toBeLessThan(8)

    // Fit view frames everything.
    await map.getByRole('button', { name: 'Fit View' }).click()
    await expect(shape(map, 'Agency')).toBeInViewport()
  })

  test('with OPERATES selected, the breaking classes stay readable with their severity outline', async ({ page }) => {
    await page.goto('/ui/kg/city-transit/versions/3/changes?select=relation:OPERATES')
    const map = ontologyMap(page)
    const drawn = (label: string) =>
      shape(map, label).evaluate((el: HTMLElement) => ({
        context: el.dataset.context === 'true',
        faded: el.dataset.faded === 'true',
        opacity: Number(getComputedStyle(el).opacity),
        outlined: getComputedStyle(el).boxShadow !== 'none',
      }))

    for (const label of ['Trip', 'Stop']) {
      await expect.poll(() => drawn(label)).toEqual({ context: true, faded: false, opacity: 0.6, outlined: true })
    }
    // SERVES did not change: it fades out of the focus.
    await expect
      .poll(() => linkPath(map, '(Trip)-[SERVES]->(Stop)').evaluate((el: SVGElement) => Number(el.style.opacity)))
      .toBe(0.3)
  })
})
