import { type Page } from '@playwright/test'
import { expect, test } from './fixtures'

const relationsSection = (page: Page) => page.getByRole('region', { name: 'Relations' })
const relations = (page: Page) => page.getByRole('table', { name: 'Relations' })
/** The Relations grid's rows by their first cell, the relation name. */
const relationNames = (page: Page) => relations(page).getByRole('row').locator('td:first-child')

test.describe('on the retail Ontology', () => {
  test.use({ seed: 'ontology_map_search' })

  test('filtering the Relations grid by a class name finds the relations whose Patterns name it', async ({
    page,
  }) => {
    await page.goto('/ui/kg/retail/versions/1/ontology?view=table')
    await expect(relationNames(page)).toHaveText(['FULFILLS', 'SHIPPED_FROM', 'STORED_IN'])
    await expect(page.getByText('3 relations', { exact: true })).toBeVisible()

    await relations(page).getByRole('button', { name: 'Filter Patterns' }).click()
    await page.getByRole('textbox', { name: 'Filter Patterns' }).fill('warehouse')
    await page.keyboard.press('Escape')
    await expect(relationNames(page)).toHaveText(['SHIPPED_FROM', 'STORED_IN'])
    await expect(relations(page).getByRole('row').nth(2)).toHaveText(/\(Bin\)-\[STORED_IN\]->\(Warehouse\)/)
    await expect(page.getByText('2 of 3 relations')).toBeVisible()
    await expect(page).toHaveURL(/relations\.f\.patterns=warehouse/)

    await page.reload()
    await expect(relationNames(page)).toHaveText(['SHIPPED_FROM', 'STORED_IN'])
  })
})

test.describe('on a described Ontology', () => {
  test.use({ seed: 'ontology_map_details' })

  test('the Relations grid shows its columns, sorts by attribute count and searches, kept in the URL', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/1/ontology?view=table')
    await expect(relations(page).getByRole('row')).toHaveText([
      /Relation.*Patterns.*Attributes.*Description/,
      /^ABOUT\s*\(Ticket\)-\[ABOUT\]->\(Product\)\s*0/,
      /^OPENED\s*\(Customer\)-\[OPENED\]->\(Ticket\)\s*1\s*The customer opened the ticket$/,
    ])

    const attributes = relations(page).getByRole('button', { name: 'Attributes' })
    await attributes.click()
    await expect(relationNames(page)).toHaveText(['OPENED', 'ABOUT'])
    await expect(page).toHaveURL(/relations\.sort=-attributes/)

    // The Concept search matches a relation's name or description.
    await page.getByRole('searchbox', { name: 'Search Concepts' }).fill('customer opened')
    await expect(relationNames(page)).toHaveText(['OPENED'])
    await expect(page.getByText('1 of 2 relations')).toBeVisible()

    await page.reload()
    await expect(relationNames(page)).toHaveText(['OPENED'])
    await expect(relations(page).getByRole('columnheader', { name: /Attributes/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
  })
})

test.describe('on the Map’s Ontology', () => {
  test.use({ seed: 'ontology_map' })

  test('Deprecated is in the Relations column picker and filters by a toggle', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/1/ontology?view=table')
    await expect(relations(page).getByRole('columnheader', { name: /Deprecated/ })).toHaveCount(0)

    await relationsSection(page).getByRole('button', { name: 'Columns' }).click()
    await page.getByRole('menuitemcheckbox', { name: 'Deprecated' }).click()
    await page.keyboard.press('Escape')
    await expect(relations(page).getByRole('columnheader', { name: /Deprecated/ })).toBeVisible()
    await expect(page).toHaveURL(/relations\.col=deprecated/)

    await relations(page).getByRole('button', { name: 'Filter Deprecated' }).click()
    await page.getByRole('switch', { name: 'Only deprecated' }).click()
    await page.keyboard.press('Escape')
    await expect(relationNames(page)).toHaveText([/^FILED/])
    await page.reload()
    await expect(relationNames(page)).toHaveText([/^FILED/])
  })
})
