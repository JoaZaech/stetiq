import { type Page } from '@playwright/test'
import { expect, test } from './fixtures'

const classes = (page: Page) => page.getByRole('table', { name: 'Classes' })
/** The Classes grid's rows by their first cell, the class name. */
const classNames = (page: Page) => classes(page).getByRole('row').locator('td:first-child')

test.describe('on support v3', () => {
  test.use({ seed: 'support_lineage' })

  test('the Table stacks collapsible sections, each with its purpose, under a jump bar with counts', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/3/ontology?view=table')

    const jumpBar = page.getByRole('navigation', { name: 'Ontology sections' })
    await expect(jumpBar).toHaveText(/Classes\s*4\s*·\s*Relations\s*1\s*·\s*Attributes\s*3/)
    await expect(page.getByText(/^Classes are the kinds of things the Knowledge Graph stores/)).toBeVisible()
    await expect(page.getByText(/^Relations say how classes connect/)).toBeVisible()
    await expect(page.getByText(/^Attributes are the fields stored on a class or relation/)).toBeVisible()

    const toggle = page.getByRole('button', { name: 'Classes', exact: true })
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await toggle.click()
    await expect(classes(page)).toBeHidden()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')

    // The jump bar opens the section it jumps to.
    await jumpBar.getByRole('button', { name: /Classes/ }).click()
    await expect(classes(page)).toBeVisible()
  })

  test('the Classes grid sorts, filters and searches, and a reload keeps all three', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/3/ontology?view=table')
    await expect(classNames(page)).toHaveText(['Party', 'Agent', 'Customer', 'Ticket'])
    await expect(page.getByText('4 classes', { exact: true })).toBeVisible()

    // Sort by own attribute count: most first, then fewest first.
    const attributes = classes(page).getByRole('button', { name: 'Attributes' })
    await attributes.click()
    await expect(classNames(page)).toHaveText(['Ticket', 'Party', 'Agent', 'Customer'])
    await attributes.click()
    await expect(classNames(page)).toHaveText(['Agent', 'Customer', 'Party', 'Ticket'])
    await expect(page).toHaveURL(/classes\.sort=attributes/)
    await attributes.click()
    await attributes.click()
    await expect(page).toHaveURL(/classes\.sort=-attributes/)

    // Filter the superclass by a value from the list.
    await classes(page).getByRole('button', { name: 'Filter Superclass' }).click()
    await page.getByRole('checkbox', { name: 'Party' }).click()
    await page.keyboard.press('Escape')
    await expect(classNames(page)).toHaveText(['Agent', 'Customer'])
    await expect(page.getByText('2 of 4 classes')).toBeVisible()
    await expect(page).toHaveURL(/classes\.f\.parent=Party/)

    // The Concept search matches names and descriptions.
    await page.getByRole('searchbox', { name: 'Search Concepts' }).fill('tickets')
    await expect(classNames(page)).toHaveText(['Customer'])
    await expect(page.getByText('1 of 4 classes')).toBeVisible()

    await page.reload()
    await expect(page.getByRole('searchbox', { name: 'Search Concepts' })).toHaveValue('tickets')
    await expect(classNames(page)).toHaveText(['Customer'])
    await expect(page.getByText('1 of 4 classes')).toBeVisible()
    await expect(classes(page).getByRole('columnheader', { name: /Attributes/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
    await expect(classes(page).getByRole('button', { name: 'Filter Superclass (on)' })).toBeVisible()

    // Clearing the search leaves the filter; clearing the filter brings every class back.
    await page.getByRole('searchbox', { name: 'Search Concepts' }).fill('')
    await expect(classNames(page)).toHaveText(['Agent', 'Customer'])
    await classes(page).getByRole('button', { name: 'Filter Superclass (on)' }).click()
    await page.getByRole('button', { name: 'Clear filter' }).click()
    await page.keyboard.press('Escape')
    await expect(classNames(page)).toHaveText(['Ticket', 'Party', 'Agent', 'Customer'])
  })
})

test.describe('on the Map’s Ontology', () => {
  test.use({ seed: 'ontology_map' })

  test('Deprecated is in the column picker and filters by a toggle; relations filter by text', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/1/ontology?view=table')
    await expect(classes(page).getByRole('columnheader', { name: /Deprecated/ })).toHaveCount(0)

    await page.getByRole('region', { name: 'Classes' }).getByRole('button', { name: 'Columns' }).click()
    await page.getByRole('menuitemcheckbox', { name: 'Deprecated' }).click()
    await page.keyboard.press('Escape')
    await expect(classes(page).getByRole('columnheader', { name: /Deprecated/ })).toBeVisible()
    await expect(page).toHaveURL(/classes\.col=deprecated/)

    await classes(page).getByRole('button', { name: 'Filter Deprecated' }).click()
    await page.getByRole('switch', { name: 'Only deprecated' }).click()
    await page.keyboard.press('Escape')
    await expect(classNames(page)).toHaveText([/^LegacyTicket/])
    await page.reload()
    await expect(classNames(page)).toHaveText([/^LegacyTicket/])
    await expect(classes(page).getByRole('row').nth(1)).toHaveText(/FILED ← Customer/)

    await page.goto('/ui/kg/support/versions/1/ontology?view=table')
    await classes(page).getByRole('button', { name: 'Filter Outgoing' }).click()
    await page.getByRole('textbox', { name: 'Filter Outgoing' }).fill('→ ticket')
    await page.keyboard.press('Escape')
    await expect(classNames(page)).toHaveText(['Customer', 'Ticket'])
  })
})
