import { expect, test } from './fixtures'

// support_task_readiness: on v3, customer-names and agent-names are answerable,
// refund-amounts is unanswerable and satisfaction is unmapped; the Triage bot's one Task,
// route-ticket, needs those four, and ticket-count serves no Task.
test.use({ seed: 'support_task_readiness' })

test('a Consumer tile says how many of its Tasks the latest Ontology Version is ready for', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  const bot = page.getByRole('region', { name: 'Consumers' }).getByRole('article', { name: 'Triage bot' })
  await expect(bot).toContainText('0 of 1 Tasks ready')
  await expect(bot).not.toContainText(/unmapped|questions answerable/)
})

test('the Consumer sheet shows each Task’s readiness, and its questions with their status', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')
  await page.getByRole('button', { name: 'Triage bot' }).click()
  const sheet = page.getByRole('dialog', { name: 'Triage bot' })

  const route = sheet.getByRole('button', { name: /Route a new ticket to an agent/ })
  await expect(route.getByRole('img', { name: "Not ready: 1 unanswerable, 1 can't check" })).toBeVisible()
  await route.click()
  await expect(
    sheet.getByRole('list', { name: 'Competency Questions route-ticket needs' }).getByRole('listitem'),
  ).toHaveText([
    /What are our agents called\?.*Answerable/,
    /What are our customers called\?.*Answerable/,
    /How much was refunded per ticket\?.*Unanswerable/,
    /How satisfied is each customer\?.*Can't check/,
  ])
  await expect(sheet).not.toContainText('unmapped')
})

test('the Competency Questions list marks the questions no Task uses', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  const list = page.getByRole('list', { name: 'Competency Questions' })
  await expect(list.getByText('Not used by any Task')).toHaveCount(1)
  await expect(list.getByRole('listitem').filter({ hasText: 'How many tickets are there?' })).toContainText(
    'Not used by any Task',
  )
})
