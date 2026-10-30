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
