import { expect, test } from './fixtures'

test.use({ seed: 'support_task_readiness' })

test('each Task on a Consumer card shows how many of its questions the latest Ontology Version answers', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/use-case')

  const bot = page.getByRole('region', { name: 'Consumers' }).getByRole('article', { name: 'Triage bot' })
  const readiness = bot.getByRole('group', { name: 'Readiness of route-ticket' })
  await expect(readiness).toContainText('2/4 questions answerable on v3')
  await expect(readiness).toContainText('1 unanswerable')
  await expect(readiness).toContainText('1 unmapped')
})

test('the Competency Questions table marks the questions that serve no Task', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  const table = page.getByRole('table', { name: 'Competency Questions' })
  await expect(table.getByText('serves no Task')).toHaveCount(1)
  await expect(table.getByRole('row').filter({ hasText: 'ticket-count' })).toContainText('serves no Task')
})
