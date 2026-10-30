import { expect, test } from './fixtures'
import type { Page } from '@playwright/test'

// support_lineage: Use Case Version 1 asks `customer-names` (concepts Customer.name).
test.use({ seed: 'support_lineage' })

const latestVersion = (page: Page) =>
  page.getByRole('region', { name: /^Use Case Version \d+$/ })

test('an editor adds a Competency Question, which creates a new Use Case Version', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/use-case')
  await expect(latestVersion(page)).toHaveAccessibleName('Use Case Version 1')

  await page.getByRole('button', { name: 'Add Competency Question' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Competency Question' })
  await dialog.getByRole('textbox', { name: 'Id' }).fill('ticket-dates')
  await dialog.getByRole('textbox', { name: 'Question' }).fill('When was each ticket opened?')
  await dialog.getByRole('textbox', { name: 'Cypher query' }).fill('MATCH (t:Ticket) RETURN t.opened_at')
  await dialog.getByRole('textbox', { name: 'Expected answer' }).fill('[{"opened_at": "2026-01-01"}]')
  await dialog.getByRole('textbox', { name: 'Concept mapping' }).fill('Ticket.opened_at')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  const latest = page.getByRole('region', { name: 'Use Case Version 2' })
  const rows = latest.getByRole('table', { name: 'Competency Questions' }).getByRole('row')
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(2)).toHaveText(
    /ticket-dates.*When was each ticket opened\?.*MATCH \(t:Ticket\) RETURN t\.opened_at.*"opened_at": "2026-01-01".*Ticket\.opened_at/s,
  )
  await expect(page.getByRole('status')).toHaveText(/Saved as Use Case Version 2/)
  await page.reload()
  await expect(page.getByRole('table', { name: 'Use Case Versions' }).getByRole('row')).toHaveCount(3)
})
