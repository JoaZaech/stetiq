import { expect, test } from './fixtures'

test.describe('with a Use Case that declares Consumers', () => {
  test.use({ seed: 'support_use_case_consumers' })

  test('the Use Case page shows a card per Consumer with its Tasks and the questions they need', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    const consumers = page.getByRole('region', { name: 'Consumers' })
    await expect(consumers.getByRole('article')).toHaveCount(2)

    const bot = consumers.getByRole('article', { name: 'Triage bot' })
    await expect(bot.getByText('agent', { exact: true })).toBeVisible()
    await expect(bot.getByText('Contact: Ada Lovelace')).toBeVisible()
    await expect(bot.getByText('Routes new tickets to the right team.')).toBeVisible()
    const tasks = bot.getByRole('list', { name: 'Tasks' }).locator(':scope > li')
    await expect(tasks).toHaveCount(2)
    await expect(tasks.nth(0)).toContainText('Greet the customer by name')
    const route = tasks.filter({ hasText: 'Route a new ticket to an agent' })
    const needed = route.getByRole('list', { name: 'Competency Questions route-ticket needs' })
    await expect(needed.getByRole('listitem')).toHaveText([
      /agent-names.*What are our agents called\?/,
      /customer-names.*What are our customers called\?/,
    ])

    const dashboard = consumers.getByRole('article', { name: 'Workload dashboard' })
    await expect(dashboard.getByText('Contact:')).toHaveCount(0)
    await expect(dashboard.getByText('List the agents on shift')).toBeVisible()
    await expect(dashboard.getByText('Needs no Competency Question')).toBeVisible()
  })
})

test.describe('with a Use Case without Consumers', () => {
  test.use({ seed: 'support_use_case_versions' })

  test('the Use Case page says no Consumers are declared', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    await expect(page.getByRole('region', { name: 'Consumers' })).toContainText(
      'No Consumers are declared in this Use Case Version.',
    )
  })
})
