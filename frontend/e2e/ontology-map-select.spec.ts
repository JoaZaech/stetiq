import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map_details' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const details = (page: Page) => page.getByRole('complementary', { name: 'Details' })

/** A class's node, or a link by its Pattern. */
const item = (map: Locator, name: string) => map.getByRole('group', { name, exact: true })
/** The drawn shape of a class's node, which carries its highlight state. */
const shape = (map: Locator, label: string) => item(map, label).locator('[data-class]')

test('selecting a class highlights its neighbours and details it, inherited attributes marked', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await item(map, 'Customer').click()

  await expect(shape(map, 'Customer')).toHaveAttribute('data-selected')
  // Ticket is a neighbour; Party (only a superclass) and Product (two links away) fade.
  await expect(shape(map, 'Ticket')).not.toHaveAttribute('data-faded')
  await expect(shape(map, 'Party')).toHaveAttribute('data-faded')
  await expect(shape(map, 'Product')).toHaveAttribute('data-faded')

  const panel = details(page)
  await expect(panel.getByRole('heading', { name: 'Customer' })).toBeVisible()
  await expect(panel).toContainText('Someone who opens tickets')
  await expect(panel.getByRole('definition').filter({ hasText: 'Party' })).toBeVisible()
  await expect(panel.getByRole('heading', { name: 'Attributes' })).toBeVisible()
  await expect(panel.getByRole('table', { name: 'Attributes' }).getByRole('row')).toHaveText([
    /Name.*Type/,
    /^email\s*STRING$/,
    /^name.*inherited from Party.*STRING.*Required$/,
  ])
  await expect(panel).toContainText('UNIQUENESS (email)')

  // Clearing the selection restores the Map.
  await panel.getByRole('button', { name: 'Close details' }).click()
  await expect(details(page)).toHaveCount(0)
  await expect(shape(map, 'Product')).not.toHaveAttribute('data-faded')

  // So does Escape.
  await item(map, 'Ticket').click()
  await expect(details(page)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(details(page)).toHaveCount(0)
})

test("selecting a link details its relation's description and attributes", async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)

  await item(map, '(Customer)-[OPENED]->(Ticket)').click()

  const panel = details(page)
  await expect(panel.getByRole('heading', { name: 'OPENED' })).toBeVisible()
  await expect(panel).toContainText('(Customer)-[OPENED]->(Ticket)')
  await expect(panel).toContainText('The customer opened the ticket')
  await expect(panel.getByRole('table', { name: 'Attributes' }).getByRole('row').nth(1)).toHaveText(
    /^channel\s*STRING$/,
  )
  await expect(shape(map, 'Product')).toHaveAttribute('data-faded')
  await expect(shape(map, 'Ticket')).not.toHaveAttribute('data-faded')
  // Attributes are never drawn on the canvas.
  await expect(map.getByText('channel')).toHaveCount(0)

  // Clicking the empty canvas clears the selection.
  await map.locator('.react-flow__pane').click({ position: { x: 5, y: 5 } })
  await expect(details(page)).toHaveCount(0)
})

test('the Concept search highlights matches on the Map and stays when switching views', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/1/ontology')
  const map = ontologyMap(page)
  const search = page.getByRole('searchbox', { name: 'Search Concepts' })

  await search.fill('product')

  await expect(page).toHaveURL('/ui/kg/support/versions/1/ontology?q=product')
  await expect(shape(map, 'Product')).toHaveAttribute('data-match')
  await expect(shape(map, 'Ticket')).not.toHaveAttribute('data-match')
  await expect(shape(map, 'Ticket')).toHaveAttribute('data-faded')

  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(search).toHaveValue('product')
  await expect(page.getByRole('table', { name: 'Classes' }).getByRole('row')).toHaveCount(2)

  await page.getByRole('radio', { name: 'Map' }).click()
  await expect(search).toHaveValue('product')
  await expect(shape(map, 'Product')).toHaveAttribute('data-match')

  await search.fill('')
  await expect(shape(map, 'Ticket')).not.toHaveAttribute('data-faded')
})
