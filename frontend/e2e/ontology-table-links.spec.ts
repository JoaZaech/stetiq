import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_details' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const details = (page: Page) => page.getByRole('complementary', { name: 'Details' })
const item = (map: Locator, name: string) => map.getByRole('group', { name, exact: true })
const shape = (map: Locator, label: string) => item(map, label).locator('[data-class]')

const classes = (page: Page) => page.getByRole('table', { name: 'Classes' })
const relations = (page: Page) => page.getByRole('table', { name: 'Relations' })
const attributes = (page: Page) => page.getByRole('table', { name: 'Attributes' })
/** A grid's row by the name in its first cell. */
const row = (table: Locator, name: string) =>
  table.getByRole('row').filter({ has: table.page().locator('td:first-child', { hasText: new RegExp(`^${name}`) }) })

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

test('a class or relation name anywhere in the Table links to its row, and a reload keeps it', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology?view=table')

  // A superclass name.
  await row(classes(page), 'Customer').getByRole('link', { name: 'Party' }).click()
  await expect(page).toHaveURL(/select=class%3AParty/)
  await expect(row(classes(page), 'Party')).toHaveAttribute('aria-current', 'true')
  await expect(row(classes(page), 'Customer')).not.toHaveAttribute('aria-current')

  // A relation in Outgoing.
  await row(classes(page), 'Customer').getByRole('link', { name: 'OPENED' }).click()
  await expect(row(relations(page), 'OPENED')).toHaveAttribute('aria-current', 'true')
  await expect(row(relations(page), 'OPENED')).toBeInViewport()
  await expect(row(classes(page), 'Party')).not.toHaveAttribute('aria-current')

  // A class in a Pattern, from a collapsed Classes section.
  await page.getByRole('button', { name: 'Classes', exact: true }).click()
  await row(relations(page), 'ABOUT').getByRole('link', { name: 'Product' }).click()
  await expect(classes(page)).toBeVisible()
  await expect(row(classes(page), 'Product')).toHaveAttribute('aria-current', 'true')
  await expect(row(classes(page), 'Product')).toBeInViewport()

  // An owner in an attribute group's header.
  await attributes(page).getByRole('row', { name: /^Ticket · class/ }).getByRole('link', { name: 'Ticket' }).click()
  await expect(row(classes(page), 'Ticket')).toHaveAttribute('aria-current', 'true')

  await page.reload()
  await expect(row(classes(page), 'Ticket')).toHaveAttribute('aria-current', 'true')
  await expect(row(classes(page), 'Ticket')).toBeInViewport()
})

test('an attribute count opens its owner’s group', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology?view=table&attributes.group=type')

  await row(relations(page), 'OPENED').getByRole('link', { name: '1 attribute' }).click()

  await expect(page).toHaveURL(/^(?!.*attributes\.group)/)
  const group = attributes(page).getByRole('button', { name: /^OPENED · relation · 1 attribute$/ })
  await expect(group).toHaveAttribute('aria-expanded', 'true')
  await expect(group).toBeInViewport()

  // A collapsed group opens again.
  await group.click()
  await expect(group).toHaveAttribute('aria-expanded', 'false')
  await row(relations(page), 'OPENED').getByRole('link', { name: '1 attribute' }).click()
  await expect(group).toHaveAttribute('aria-expanded', 'true')

  // A class's count opens its group, inherited attributes included; no attributes, no link.
  await row(classes(page), 'Customer').getByRole('link', { name: '2 attributes' }).click()
  await expect(attributes(page).getByRole('button', { name: /^Customer · class/ })).toBeInViewport()
  await expect(row(classes(page), 'Product').getByRole('link', { name: /attribute/ })).toHaveCount(0)
})

test('"Show on Map" opens the Map with the Concept selected and centred', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology?view=table')

  await row(classes(page), 'Product').getByRole('button', { name: 'Show Product on Map' }).click()

  await expect(page).toHaveURL(/\/ontology\?select=class%3AProduct$/)
  const map = ontologyMap(page)
  await expect(shape(map, 'Product')).toHaveAttribute('data-selected')
  await expect(details(page).getByRole('heading', { name: 'Product' })).toBeVisible()
  await expect.poll(() => offCentre(page, 'Product')).toBeLessThan(4)

  // A relation shows as its Pattern link.
  await page.goBack()
  await row(relations(page), 'OPENED').getByRole('button', { name: 'Show OPENED on Map' }).click()
  await expect(details(page).getByRole('heading', { name: 'OPENED' })).toBeVisible()
  await expect(details(page)).toContainText('(Customer)-[OPENED]->(Ticket)')
})

test('the selection carries between the Map and the Table both ways, and survives a reload', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await item(map, 'Customer').click()
  await expect(page).toHaveURL(/select=class%3ACustomer/)
  await page.reload()
  await expect(shape(ontologyMap(page), 'Customer')).toHaveAttribute('data-selected')
  await expect(details(page).getByRole('heading', { name: 'Customer' })).toBeVisible()

  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(row(classes(page), 'Customer')).toHaveAttribute('aria-current', 'true')

  // A link selected on the Map highlights its relation.
  // The Map opens centred on the selection: fit it to reach the link.
  await page.getByRole('radio', { name: 'Map' }).click()
  await expect(shape(ontologyMap(page), 'Customer')).toHaveAttribute('data-selected')
  await ontologyMap(page).getByRole('button', { name: 'Fit View' }).click()
  await item(ontologyMap(page), '(Ticket)-[ABOUT]->(Product)').click()
  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(row(relations(page), 'ABOUT')).toHaveAttribute('aria-current', 'true')
  await expect(row(classes(page), 'Customer')).not.toHaveAttribute('aria-current')

  // And a name picked in the Table is selected on the Map.
  await row(classes(page), 'Ticket').getByRole('link', { name: 'Ticket' }).click()
  await page.getByRole('radio', { name: 'Map' }).click()
  await expect(shape(ontologyMap(page), 'Ticket')).toHaveAttribute('data-selected')

  // Clearing the selection on the Map clears it from the URL.
  await page.keyboard.press('Escape')
  await expect(page).not.toHaveURL(/select=/)
})
