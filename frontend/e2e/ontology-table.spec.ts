import { type Page } from '@playwright/test'
import { expect, test } from './fixtures'

const classes = (page: Page) => page.getByRole('table', { name: 'Classes' })
/** The Classes grid's rows by their first cell, the class name. */
const classNames = (page: Page) => classes(page).getByRole('row').locator('td:first-child')
const attributes = (page: Page) => page.getByRole('table', { name: 'Attributes' })

test.describe('on support v3', () => {
  test.use({ seed: 'support_lineage' })

  test('the Table stacks collapsible sections, each with its purpose, under a jump bar with counts', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/3/ontology?view=table')

    const jumpBar = page.getByRole('navigation', { name: 'Ontology sections' })
    // Attributes counts the grid's rows, inherited ones included, and says so as the grid does.
    await expect(jumpBar).toHaveText(/Classes\s*4\s*·\s*Relations\s*1\s*·\s*Attributes\s*5/)
    await expect(jumpBar.getByRole('button', { name: /Attributes/ })).toHaveAttribute('title', '5 attributes')
    await expect(page.getByText('5 attributes', { exact: true })).toBeVisible()
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

  test('the Attributes grid groups by owner, with inherited attributes marked, and by type or not at all', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/3/ontology?view=table')
    await expect(attributes(page).getByRole('row')).toHaveText([
      /^Owner\s*Attribute\s*Type\s*Required\s*Unique\s*Description$/,
      /^Party · class · 1 attribute$/,
      // The owner is its group's header, not repeated on each row.
      /^name\s*STRING\s*Required$/,
      /^Agent · class · subclass of Party · 1 attribute$/,
      /^name\s*from Party\s*STRING\s*Required$/,
      /^Customer · class · subclass of Party · 1 attribute$/,
      /^name\s*from Party\s*STRING\s*Required\s*Unique$/,
      /^Ticket · class · 2 attributes$/,
      /^opened_at\s*DATE$/,
      /^priority\s*INTEGER$/,
    ])
    await expect(page.getByText('5 attributes', { exact: true })).toBeVisible()

    // A group collapses to its header.
    const ticket = attributes(page).getByRole('button', { name: /^Ticket · class/ })
    await ticket.click()
    await expect(ticket).toHaveAttribute('aria-expanded', 'false')
    await expect(attributes(page).getByRole('row')).toHaveCount(8)
    await ticket.click()

    // Filters and search work within the groups.
    await attributes(page).getByRole('button', { name: 'Filter Unique' }).click()
    await page.getByRole('switch', { name: 'Only unique' }).click()
    await page.keyboard.press('Escape')
    await expect(attributes(page).getByRole('row')).toHaveText([/^Owner/, /^Customer · class/, /^name/])
    await expect(page.getByText('1 of 5 attributes')).toBeVisible()
    await attributes(page).getByRole('button', { name: 'Filter Unique (on)' }).click()
    await page.getByRole('button', { name: 'Clear filter' }).click()
    await page.keyboard.press('Escape')

    const groupBy = page.getByRole('radiogroup', { name: 'Group attributes by' })
    await groupBy.getByRole('radio', { name: 'Type' }).click()
    await expect(page).toHaveURL(/attributes\.group=type/)
    await expect(attributes(page).getByRole('row')).toHaveText([
      /^Owner/,
      /^STRING · 3 attributes$/,
      /^Party\s*name\s*Required$/,
      /^Agent\s*name\s*from Party\s*Required$/,
      /^Customer\s*name\s*from Party\s*Required\s*Unique$/,
      /^DATE · 1 attribute$/,
      /^Ticket\s*opened_at$/,
      /^INTEGER · 1 attribute$/,
      /^Ticket\s*priority$/,
    ])

    await groupBy.getByRole('radio', { name: 'None' }).click()
    await page.reload()
    await expect(page.getByRole('radiogroup', { name: 'Group attributes by' }).getByRole('radio', { name: 'None' })).toBeChecked()
    await expect(attributes(page).getByRole('row')).toHaveText([
      /^Owner/,
      /^Party\s*name\s*STRING/,
      /^Agent\s*name\s*from Party\s*STRING/,
      /^Customer\s*name\s*from Party\s*STRING/,
      /^Ticket\s*opened_at\s*DATE/,
      /^Ticket\s*priority\s*INTEGER/,
    ])

    // Inherited from and Owner kind are in the column picker.
    await page.getByRole('region', { name: 'Attributes' }).getByRole('button', { name: 'Columns' }).click()
    await page.getByRole('menuitemcheckbox', { name: 'Inherited from' }).click()
    await page.keyboard.press('Escape')
    await expect(attributes(page).getByRole('row').nth(2)).toHaveText(/^Agent\s*name\s*from Party\s*STRING\s*Required\s*Party/)
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
