import { expect, test } from './fixtures'

test.describe('with a Use Case that declares Consumers', () => {
  test.use({ seed: 'support_consumer_impact' })

  for (const view of ['map', 'table'] as const) {
    test(`the ${view} comparison lists an item per Task the Diff affects and will affect, the worst first`, async ({
      page,
    }) => {
      await page.goto(`/ui/kg/support/versions/compare?id=2&id=4${view === 'table' ? '&view=table' : ''}`)

      const impact = page.getByRole('region', { name: 'Consumer impact' })
      const items = impact.getByRole('list', { name: 'Tasks and questions hit' }).locator(':scope > li')

      // Triage bot is affected by the removed Ticket.opened_at; its other Task, and Workload
      // dashboard's, only will be, by the deprecated Agent. A question nothing maps comes last.
      await expect(items).toHaveText([
        /^Affected: Route a new ticket by its age\s*Triage bot\s*breaks Ticket\.opened_at/,
        /^Will be affected: Assign the ticket to an agent\s*Triage bot\s*deprecates Agent/,
        /^Will be affected: Chart each agent's workload\s*Workload dashboard\s*deprecates Agent/,
        /^Impact unknown: Which customers are the most loyal\?\s*No Consumer\s*can't tell: no Concept mapping or query$/,
      ])
      // CRM sync needs nothing that changed; no machine id is shown.
      await expect(impact.getByText('CRM sync')).toHaveCount(0)
      for (const id of ['triage-bot', 'route-ticket', 'ticket-dates', 'loyal-customers']) {
        await expect(impact).not.toContainText(id)
      }

      // An item expands in place to the questions it hits and the Concepts that hit them.
      const route = impact.getByRole('listitem', { name: 'Route a new ticket by its age' })
      const questions = route.getByRole('list', { name: 'Competency Questions hit' })
      await expect(questions).toBeHidden()
      await route.getByRole('button').click()
      await expect(route.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
      await expect(questions.locator(':scope > li')).toHaveText([
        /^When was each ticket opened\?\s*Ticket\.opened_at \(breaking\)$/,
      ])

      // A question no Task needs is already its own title: it does not expand.
      await expect(impact.getByRole('listitem', { name: 'Which customers are the most loyal?' }).getByRole('button')).toHaveCount(0)
    })
  }

  test('the Changes tab says so when no Consumer is affected', async ({ page }) => {
    // v1 -> v2 only adds, so nothing is hit.
    await page.goto('/ui/kg/support/versions/2/changes')

    const impact = page.getByRole('region', { name: 'Consumer impact' })
    await expect(impact).toHaveText(/^Consumer impact\s*No Consumer is affected$/)
    await expect(impact.getByRole('list')).toHaveCount(0)
  })
})

test.describe('without a Use Case', () => {
  test.use({ seed: 'ontology_map' })

  test('the comparison says there are no Consumers to judge the change against', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/compare?id=1&id=2&view=table')

    await expect(page.getByRole('region', { name: 'Consumer impact' })).toContainText(
      'This Knowledge Graph has no Use Case',
    )
    await expect(page.getByRole('region', { name: 'Ontology Diff' })).toBeVisible()
  })
})
