import { expect, test } from './fixtures'

test.describe('with three Use Case Versions', () => {
  test.use({ seed: 'support_use_case_versions' })

  test('the Use Case page lists the latest Use Case Version’s Competency Questions with their status', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
    await expect(page.getByRole('heading', { level: 2, name: 'Use Case' })).toBeVisible()
    const latest = page.getByRole('region', { name: 'Use Case Version 3' })
    await expect(latest.getByText('Support agents triage and answer tickets')).toBeVisible()

    await expect(latest.getByText('Ontology Version v3 answers 2 of 2 Competency Questions.')).toBeVisible()
    const questions = latest.getByRole('list', { name: 'Competency Questions' }).getByRole('listitem')
    await expect(questions).toHaveText([
      /What is each customer called\?\s*Not used by any Task\s*Answerable/,
      /When was each ticket opened\?\s*Not used by any Task\s*Answerable/,
    ])
    // Ids, Cypher and expected answers stay in the sheet.
    await expect(latest).not.toContainText('ticket-dates')
    await expect(latest).not.toContainText('MATCH')
    await expect(latest).not.toContainText('opened_at')
    await expect(page.getByRole('region', { name: 'Structural answerability' })).toHaveCount(0)
  })

  test('clicking a question opens its sheet, which the URL keeps and Back closes', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    await page.getByRole('button', { name: /When was each ticket opened\?/ }).click()
    const sheet = page.getByRole('dialog', { name: 'When was each ticket opened?' })
    await expect(sheet).toContainText('Answerable on Ontology Version v3')
    await expect(sheet.getByRole('region', { name: 'Missing Concepts' })).toHaveCount(0)
    await expect(sheet.getByRole('region', { name: 'Needed by' })).toHaveText(/Not used by any Task/)
    await expect(sheet.getByRole('region', { name: 'Author details' })).toHaveText(
      /Id\s*ticket-dates\s*Cypher query\s*MATCH \(t:Ticket\) RETURN t\.opened_at\s*Expected answer\s*\[\s*\{\s*"opened_at": "2026-01-01"\s*\}\s*\]\s*Concept mapping\s*Ticket\.opened_at/,
    )
    await expect(page).toHaveURL(/\/ui\/kg\/support\/use-case\?sheet=question%3Aticket-dates$/)

    await page.reload()
    await expect(sheet).toBeVisible()

    await page.goBack()
    await expect(sheet).toBeHidden()
    await expect(page).toHaveURL(/\/ui\/kg\/support\/use-case$/)

    // A link opens it too; closing it leaves the URL clean.
    await page.goto('/ui/kg/support/use-case?sheet=question:customer-names')
    const customers = page.getByRole('dialog', { name: 'What is each customer called?' })
    await expect(customers).toBeVisible()
    await customers.getByRole('button', { name: 'Close' }).click()
    await expect(customers).toBeHidden()
    await expect(page).toHaveURL(/\/ui\/kg\/support\/use-case$/)
  })

  test('the Use Case Versions list compares two versions question by question', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const versions = page.getByRole('table', { name: 'Use Case Versions' })
    const rows = versions.getByRole('row')
    await expect(rows).toHaveCount(4)
    await expect(rows.nth(1)).toHaveText(/v3.*2 Competency Questions/)
    await expect(rows.nth(3)).toHaveText(/v1.*1 Competency Question\b/)

    const compare = page.getByRole('button', { name: 'Compare' })
    await expect(compare).toBeDisabled()
    await versions.getByRole('checkbox', { name: 'Select v2' }).check()
    await versions.getByRole('checkbox', { name: 'Select v3' }).check()
    await compare.click()

    await expect(page).toHaveURL('/ui/kg/support/use-case/compare?id=2&id=3')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare v2 → v3')
    await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
      /Knowledge Graphs.*support.*Use Case.*Compare/,
    )

    const added = page.getByRole('region', { name: 'Added' })
    await expect(added.getByText('ticket-dates')).toBeVisible()
    await expect(added.getByText('When was each ticket opened?')).toBeVisible()

    const removed = page.getByRole('region', { name: 'Removed' })
    await expect(removed.getByText('agent-names')).toBeVisible()

    const changed = page.getByRole('region', { name: 'Changed' })
    const change = changed.getByRole('table', { name: 'customer-names' })
    await expect(change.getByRole('row')).toHaveCount(2)
    await expect(change.getByRole('row').nth(1)).toHaveText(
      /Question.*What are our customers called\?.*What is each customer called\?/,
    )
    await expect(page.getByRole('region', { name: 'Description' })).toContainText(
      /Support agents triage tickets.*Support agents triage and answer tickets/,
    )
  })

  test('comparing a version with itself shows no changes', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case/compare?id=1&id=1')

    await expect(page.getByText('These Use Case Versions ask the same Competency Questions.')).toBeVisible()
  })
})

test.describe('without a Use Case', () => {
  test.use({ seed: 'knowledge_graphs' })

  test('the Use Case page says no Use Case has been registered', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    await expect(page.getByRole('heading', { level: 2, name: 'Use Case' })).toBeVisible()
    await expect(page.getByText('No Use Case has been registered yet.')).toBeVisible()
    await expect(page.getByRole('list', { name: 'Competency Questions' })).toHaveCount(0)
    await expect(page.getByRole('table')).toHaveCount(0)
  })
})
