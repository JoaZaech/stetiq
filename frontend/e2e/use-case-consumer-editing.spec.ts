import { expect, signIn, test } from './fixtures'
import type { Page } from '@playwright/test'

// support_use_case_consumers: Use Case Version 2 asks agent-names and customer-names; the
// Triage bot's Tasks are greet-customer (customer-names) and route-ticket (both), the
// Workload dashboard's show-agents needs none.
test.use({ seed: 'support_use_case_consumers' })

const consumers = (page: Page) => page.getByRole('region', { name: 'Consumers' })
const card = (page: Page, name: string) => consumers(page).getByRole('article', { name })
const questionRows = (page: Page, version: number) =>
  page
    .getByRole('region', { name: `Use Case Version ${version}` })
    .getByRole('table', { name: 'Competency Questions' })
    .getByRole('row')

test('an editor adds a Consumer, which creates a new Use Case Version', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Add Consumer' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Consumer' })
  await dialog.getByRole('textbox', { name: 'Id' }).fill('billing-app')
  await dialog.getByRole('textbox', { name: 'Name' }).fill('Billing app')
  await dialog.getByRole('textbox', { name: 'Kind' }).fill('application')
  await dialog.getByRole('textbox', { name: 'Contact' }).fill('Grace Hopper')
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Bills customers per ticket.')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(consumers(page).getByRole('article')).toHaveCount(3)
  const billing = card(page, 'Billing app')
  await expect(billing.getByText('application', { exact: true })).toBeVisible()
  await expect(billing.getByText('Contact: Grace Hopper')).toBeVisible()
  await expect(billing.getByText('Bills customers per ticket.')).toBeVisible()
  await expect(billing.getByText('No Tasks')).toBeVisible()
  await page.reload()
  await expect(card(page, 'Billing app')).toBeVisible()
})

test('a Consumer id another Consumer, Task or question has is refused, and nothing is saved', async ({
  page,
}) => {
  const writes: string[] = []
  page.on('request', (r) => {
    if (r.method() !== 'GET') writes.push(r.url())
  })
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Add Consumer' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Consumer' })
  const id = dialog.getByRole('textbox', { name: 'Id' })
  await id.fill('route-ticket')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(id).toHaveAttribute('aria-invalid', 'true')
  await expect(id).toHaveAccessibleDescription(/The Task route-ticket already has this id\./)
  await expect(dialog.getByRole('textbox', { name: 'Name' })).toHaveAccessibleDescription('Needs a name.')
  await id.fill('customer-names')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(id).toHaveAccessibleDescription(/The Competency Question customer-names already has this id\./)
  expect(writes).toEqual([])
})

test('an editor edits a Consumer, whose id is read-only, keeping its Tasks', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Edit Consumer triage-bot' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit Consumer triage-bot' })
  const id = dialog.getByRole('textbox', { name: 'Id' })
  await expect(id).toHaveValue('triage-bot')
  await expect(id).not.toBeEditable()
  await expect(dialog.getByRole('textbox', { name: 'Contact' })).toHaveValue('Ada Lovelace')
  await dialog.getByRole('textbox', { name: 'Name' }).fill('Routing bot')
  await dialog.getByRole('textbox', { name: 'Contact' }).fill('')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  const bot = card(page, 'Routing bot')
  await expect(bot.getByText('Contact:')).toHaveCount(0)
  await expect(bot.getByRole('list', { name: 'Tasks' }).locator(':scope > li')).toHaveCount(2)
})

test('removing a Consumer names its Tasks, and keeps the Competency Questions', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Remove Consumer triage-bot' }).click()
  const confirm = page.getByRole('alertdialog', { name: 'Remove Triage bot?' })
  await expect(confirm.getByRole('list', { name: 'Tasks removed with it' }).getByRole('listitem')).toHaveText([
    /greet-customer.*Greet the customer by name/,
    /route-ticket.*Route a new ticket to an agent/,
  ])
  await confirm.getByRole('button', { name: 'Cancel' }).click()
  await expect(consumers(page).getByRole('article')).toHaveCount(2)

  await page.getByRole('button', { name: 'Remove Consumer triage-bot' }).click()
  await confirm.getByRole('button', { name: 'Remove' }).click()

  await expect(confirm).toBeHidden()
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(consumers(page).getByRole('article')).toHaveCount(1)
  await expect(card(page, 'Workload dashboard')).toBeVisible()
  await expect(questionRows(page, 3)).toHaveCount(3)
})

test('an editor adds a Task to a Consumer, picking the questions it needs', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Add Task to workload-dashboard' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Task to Workload dashboard' })
  await dialog.getByRole('textbox', { name: 'Id' }).fill('count-agents')
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Count the agents on shift')
  const needs = dialog.getByRole('group', { name: 'Competency Questions it needs' })
  await expect(needs.getByRole('checkbox')).toHaveCount(2)
  await needs.getByRole('checkbox', { name: /agent-names/ }).check()
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  const needed = card(page, 'Workload dashboard').getByRole('list', {
    name: 'Competency Questions count-agents needs',
  })
  await expect(needed.getByRole('listitem')).toHaveText([/agent-names.*What are our agents called\?/])
})

test('a Task id already in the Use Case is refused', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Add Task to workload-dashboard' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Task to Workload dashboard' })
  const id = dialog.getByRole('textbox', { name: 'Id' })
  await id.fill('triage-bot')
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Anything')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(id).toHaveAccessibleDescription(/The Consumer triage-bot already has this id\./)
  await expect(dialog).toBeVisible()
})

test('an editor edits a Task, whose id is read-only, and unassigns a question', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Edit Task route-ticket' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit Task route-ticket' })
  await expect(dialog.getByRole('textbox', { name: 'Id' })).not.toBeEditable()
  const needs = dialog.getByRole('group', { name: 'Competency Questions it needs' })
  await expect(needs.getByRole('checkbox', { name: /agent-names/ })).toBeChecked()
  await needs.getByRole('checkbox', { name: /customer-names/ }).uncheck()
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Route a ticket')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  const tasks = card(page, 'Triage bot').getByRole('list', { name: 'Tasks' }).locator(':scope > li')
  const route = tasks.filter({ hasText: 'Route a ticket' })
  await expect(
    route.getByRole('list', { name: 'Competency Questions route-ticket needs' }).getByRole('listitem'),
  ).toHaveText([/agent-names/])
})

test('an editor removes a Task after confirming', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Remove Task greet-customer' }).click()
  await page
    .getByRole('alertdialog', { name: 'Remove greet-customer?' })
    .getByRole('button', { name: 'Remove' })
    .click()

  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  const tasks = card(page, 'Triage bot').getByRole('list', { name: 'Tasks' }).locator(':scope > li')
  await expect(tasks).toHaveCount(1)
  await expect(tasks).toContainText('Route a new ticket to an agent')
})

test('removing a question a Task needs says which Tasks lose it', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Remove customer-names' }).click()
  const confirm = page.getByRole('alertdialog', { name: 'Remove customer-names?' })
  await expect(confirm.getByRole('list', { name: 'Tasks that lose it' }).getByRole('listitem')).toHaveText([
    /greet-customer.*Greet the customer by name/,
    /route-ticket.*Route a new ticket to an agent/,
  ])
  await confirm.getByRole('button', { name: 'Remove' }).click()

  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(questionRows(page, 3)).toHaveCount(2)
  const bot = card(page, 'Triage bot')
  const tasks = bot.getByRole('list', { name: 'Tasks' }).locator(':scope > li')
  await expect(tasks.filter({ hasText: 'Greet the customer by name' })).toContainText('Needs no Competency Question')
})

test('removing a question no Task needs says nothing about Tasks', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')
  // agent-names is needed by route-ticket only; take it off first.
  await page.getByRole('button', { name: 'Remove Task route-ticket' }).click()
  await page.getByRole('alertdialog', { name: 'Remove route-ticket?' }).getByRole('button', { name: 'Remove' }).click()
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')

  await page.getByRole('button', { name: 'Remove agent-names' }).click()
  const confirm = page.getByRole('alertdialog', { name: 'Remove agent-names?' })
  await expect(confirm.getByRole('list', { name: 'Tasks that lose it' })).toHaveCount(0)
})

test.describe('signed in with a read-only API Token', () => {
  test.use({ mode: 'server', seed: 'support_use_case_consumers_reader' })

  test('every Consumer and Task edit control is disabled', async ({ page, stetiq }) => {
    await signIn(page, (stetiq.seeded.grace as { value: string }).value)
    await page.goto('/ui/kg/support/use-case')
    await expect(card(page, 'Triage bot')).toBeVisible()

    for (const name of [
      'Add Consumer',
      'Edit Consumer triage-bot',
      'Remove Consumer triage-bot',
      'Add Task to triage-bot',
      'Edit Task route-ticket',
      'Remove Task route-ticket',
    ]) {
      await expect(page.getByRole('button', { name })).toBeDisabled()
    }
    await page.getByRole('button', { name: 'Add Consumer' }).hover({ force: true })
    await expect(page.getByRole('tooltip')).toHaveText('Needs edit access')
  })
})
