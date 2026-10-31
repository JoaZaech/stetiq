import { expect, test } from './fixtures'

test.describe('with a Use Case that declares Consumers', () => {
  test.use({ seed: 'support_consumer_impact' })

  for (const view of ['map', 'table'] as const) {
    test(`the ${view} comparison lists the Consumers and Tasks the Diff affects and will affect`, async ({
      page,
    }) => {
      await page.goto(`/ui/kg/support/versions/compare?id=2&id=4${view === 'table' ? '&view=table' : ''}`)

      const impact = page.getByRole('region', { name: 'Consumer impact' })
      const affected = impact.getByRole('region', { name: 'Affected', exact: true })
      const later = impact.getByRole('region', { name: 'Will be affected' })
      const unknown = impact.getByRole('region', { name: 'Impact unknown' })

      // Triage bot is affected by the removed Ticket.opened_at; its other Task only will be.
      const bot = affected.getByRole('listitem', { name: 'Triage bot' })
      await expect(affected.getByRole('list', { name: 'Affected Consumers' }).locator(':scope > li')).toHaveCount(1)
      await expect(bot.getByText('agent', { exact: true })).toBeVisible()
      const tasks = bot.getByRole('list', { name: 'Tasks of Triage bot hit' }).locator(':scope > li')
      await expect(tasks).toHaveText([
        /Route a new ticket by its age.*route-ticket/,
        /Assign the ticket to an agent.*assign-agent.*\(will be affected\)/,
      ])
      await expect(bot.getByRole('list', { name: 'Competency Questions of route-ticket hit' })).toHaveText(
        /ticket-dates.*When was each ticket opened\?.*Ticket\.opened_at \(breaking\)/,
      )

      await expect(later.getByRole('list', { name: 'Will be affected Consumers' }).locator(':scope > li')).toHaveCount(1)
      const dashboard = later.getByRole('listitem', { name: 'Workload dashboard' })
      await expect(dashboard).toContainText('Chart each agent')
      await expect(dashboard.getByRole('list', { name: 'Competency Questions of workload-chart hit' })).toHaveText(
        /agent-names.*Agent \(deprecating\)/,
      )

      // CRM sync needs nothing that changed; a question nothing maps is never called unaffected.
      await expect(impact.getByText('CRM sync')).toHaveCount(0)
      await expect(unknown.getByRole('list', { name: 'Impact unknown questions no Task needs' })).toHaveText(
        /loyal-customers.*Which customers are the most loyal\?/,
      )
    })
  }
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
