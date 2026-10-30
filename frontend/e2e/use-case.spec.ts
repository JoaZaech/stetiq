import { expect, test } from './fixtures'

test.describe('with three Use Case Versions', () => {
  test.use({ seed: 'support_use_case_versions' })

  test('the Use Case page shows the latest Use Case Version and its Competency Questions', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
    await expect(page.getByRole('heading', { level: 2, name: 'Use Case' })).toBeVisible()
    const latest = page.getByRole('region', { name: 'Use Case Version 3' })
    await expect(latest.getByText('Support agents triage and answer tickets')).toBeVisible()

    const questions = latest.getByRole('table', { name: 'Competency Questions' })
    const rows = questions.getByRole('row')
    await expect(rows.first()).toHaveText(/Id.*Question.*Query.*Expected answer.*Concept mapping/)
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(1)).toHaveText(/customer-names.*What is each customer called\?.*Customer\.name/)
    await expect(rows.nth(2)).toHaveText(
      /ticket-dates.*When was each ticket opened\?.*MATCH \(t:Ticket\) RETURN t\.opened_at.*\[\s*\{\s*"opened_at": "2026-01-01"\s*\}\s*\].*Ticket\.opened_at/,
    )
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
    await expect(page.getByRole('table')).toHaveCount(0)
  })
})
