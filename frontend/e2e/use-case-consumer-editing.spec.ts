import { expect, signIn, test } from './fixtures'
import type { Locator, Page } from '@playwright/test'

// support_use_case_consumers: Use Case Version 2 asks agent-names and customer-names; the
// Triage bot's Tasks are greet-customer (customer-names) and route-ticket (both), the
// Workload dashboard's show-agents needs none.
test.use({ seed: 'support_use_case_consumers' })

const consumers = (page: Page) => page.getByRole('region', { name: 'Consumers' })
const tile = (page: Page, name: string) => consumers(page).getByRole('article', { name })
/** Opens a Consumer's sheet from its tile; editing a Consumer and its Tasks happens there. */
const openConsumer = async (page: Page, name: string) => {
  await tile(page, name).getByRole('button', { name }).click()
  const sheet = page.getByRole('dialog', { name })
  await expect(sheet).toBeVisible()
  return sheet
}
const tasksIn = (sheet: Locator) => sheet.getByRole('list', { name: 'Tasks' }).locator(':scope > li')
/** Expands a Task in a Consumer sheet to the questions it needs. */
const expandTask = async (sheet: Locator, description: string) => {
  await sheet.getByRole('button', { name: new RegExp(description) }).click()
  return tasksIn(sheet).filter({ hasText: description })
}
/** Shows the Questions tab and returns the question catalog's rows, without its header row. */
const questionRows = async (page: Page) => {
  await page.getByRole('tab', { name: 'Questions' }).click()
  return page.getByRole('table', { name: 'Competency Questions' }).getByRole('row').filter({ has: page.getByRole('cell') })
}

test('an editor adds a Consumer, which creates a new Use Case Version', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

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
  const billing = tile(page, 'Billing app')
  await expect(billing.getByRole('img', { name: 'application' })).toBeVisible()
  await expect(billing).toContainText('Bills customers per ticket.')
  await expect(billing).toContainText('No Tasks')
  await expect(billing).not.toContainText('Grace Hopper')

  const sheet = await openConsumer(page, 'Billing app')
  await expect(sheet).toContainText(/Kind\s*application\s*Id\s*billing-app\s*Contact\s*Grace Hopper/)
  await expect(sheet.getByRole('region', { name: 'Tasks' })).toContainText('No Tasks')
  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Billing app' })).toBeVisible()
})

test('a Consumer id another Consumer, Task or question has is refused, and nothing is saved', async ({
  page,
}) => {
  const writes: string[] = []
  page.on('request', (r) => {
    if (r.method() !== 'GET') writes.push(r.url())
  })
  await page.goto('/ui/kg/support/use-case?tab=consumers')

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

test('an editor edits a Consumer from its sheet, whose id is read-only, keeping its Tasks', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Triage bot')
  await sheet.getByRole('button', { name: 'Edit', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit Consumer triage-bot' })
  const id = dialog.getByRole('textbox', { name: 'Id' })
  await expect(id).toHaveValue('triage-bot')
  await expect(id).not.toBeEditable()
  await expect(dialog.getByRole('textbox', { name: 'Contact' })).toHaveValue('Ada Lovelace')
  await dialog.getByRole('textbox', { name: 'Name' }).fill('Routing bot')
  await dialog.getByRole('textbox', { name: 'Contact' }).fill('')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  const edited = page.getByRole('dialog', { name: 'Routing bot' })
  await expect(edited).toContainText(/Contact\s*None/)
  await expect(tasksIn(edited)).toHaveCount(2)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(tile(page, 'Routing bot')).toBeVisible()
})

test('removing a Consumer from its sheet names its Tasks, and keeps the Competency Questions', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Triage bot')
  await sheet.getByRole('button', { name: 'Remove', exact: true }).click()
  const confirm = page.getByRole('alertdialog', { name: 'Remove Triage bot?' })
  await expect(confirm.getByRole('list', { name: 'Tasks removed with it' }).getByRole('listitem')).toHaveText([
    /greet-customer.*Greet the customer by name/,
    /route-ticket.*Route a new ticket to an agent/,
  ])
  await confirm.getByRole('button', { name: 'Cancel' }).click()
  await expect(sheet).toBeVisible()

  await sheet.getByRole('button', { name: 'Remove', exact: true }).click()
  await confirm.getByRole('button', { name: 'Remove' }).click()

  await expect(confirm).toBeHidden()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page).not.toHaveURL(/sheet=/)
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(consumers(page).getByRole('article')).toHaveCount(1)
  await expect(tile(page, 'Workload dashboard')).toBeVisible()
  await expect(await questionRows(page)).toHaveCount(2)
})

test('an editor adds a Task to a Consumer from its sheet, picking the questions it needs', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Workload dashboard')
  await sheet.getByRole('button', { name: 'Add Task' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Task to Workload dashboard' })
  await dialog.getByRole('textbox', { name: 'Id' }).fill('count-agents')
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Count the agents on shift')
  const needs = dialog.getByRole('group', { name: 'Competency Questions it needs' })
  await expect(needs.getByRole('checkbox')).toHaveCount(2)
  await needs.getByRole('checkbox', { name: /agent-names/ }).check()
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  const task = await expandTask(sheet, 'Count the agents on shift')
  await expect(
    task.getByRole('list', { name: 'Competency Questions count-agents needs' }).getByRole('listitem'),
  ).toHaveText([/What are our agents called\?/])
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(tile(page, 'Workload dashboard')).toContainText('2 of 2 Tasks ready')
})

test('a Task id already in the Use Case is refused', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Workload dashboard')
  await sheet.getByRole('button', { name: 'Add Task' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Task to Workload dashboard' })
  const id = dialog.getByRole('textbox', { name: 'Id' })
  await id.fill('triage-bot')
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Anything')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(id).toHaveAccessibleDescription(/The Consumer triage-bot already has this id\./)
  await expect(dialog).toBeVisible()
})

test('an editor edits a Task from the sheet, whose id is read-only, and unassigns a question', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Triage bot')
  await sheet.getByRole('button', { name: 'Edit Task route-ticket' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit Task route-ticket' })
  await expect(dialog.getByRole('textbox', { name: 'Id' })).not.toBeEditable()
  const needs = dialog.getByRole('group', { name: 'Competency Questions it needs' })
  await expect(needs.getByRole('checkbox', { name: /agent-names/ })).toBeChecked()
  await needs.getByRole('checkbox', { name: /customer-names/ }).uncheck()
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Route a ticket')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  const route = await expandTask(sheet, 'Route a ticket')
  await expect(
    route.getByRole('list', { name: 'Competency Questions route-ticket needs' }).getByRole('listitem'),
  ).toHaveText([/What are our agents called\?/])
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
})

test('an editor removes a Task from the sheet after confirming', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Triage bot')
  await sheet.getByRole('button', { name: 'Remove Task greet-customer' }).click()
  await page
    .getByRole('alertdialog', { name: 'Remove greet-customer?' })
    .getByRole('button', { name: 'Remove' })
    .click()

  await expect(tasksIn(sheet)).toHaveCount(1)
  await expect(tasksIn(sheet)).toContainText('Route a new ticket to an agent')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(tile(page, 'Triage bot')).toContainText('1 of 1 Tasks ready')
})

test('removing a question a Task needs says which Tasks lose it', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: /^What are our customers called\?/ }).click()
  await page.getByRole('dialog', { name: 'What are our customers called?' }).getByRole('button', { name: 'Remove' }).click()
  const confirm = page.getByRole('alertdialog', { name: 'Remove customer-names?' })
  await expect(confirm.getByRole('list', { name: 'Tasks that lose it' }).getByRole('listitem')).toHaveText([
    /greet-customer.*Greet the customer by name/,
    /route-ticket.*Route a new ticket to an agent/,
  ])
  await confirm.getByRole('button', { name: 'Remove' }).click()

  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
  await expect(await questionRows(page)).toHaveCount(1)
  await page.getByRole('tab', { name: 'Consumers' }).click()
  const sheet = await openConsumer(page, 'Triage bot')
  const greet = await expandTask(sheet, 'Greet the customer by name')
  await expect(greet).toContainText('Needs no Competency Question')
})

test('removing a question no Task needs says nothing about Tasks', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')
  // agent-names is needed by route-ticket only; take it off first.
  const sheet = await openConsumer(page, 'Triage bot')
  await sheet.getByRole('button', { name: 'Remove Task route-ticket' }).click()
  await page.getByRole('alertdialog', { name: 'Remove route-ticket?' }).getByRole('button', { name: 'Remove' }).click()
  await expect(tasksIn(sheet)).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')

  await page.getByRole('tab', { name: 'Questions' }).click()
  await page.getByRole('button', { name: /^What are our agents called\?/ }).click()
  await page.getByRole('dialog', { name: 'What are our agents called?' }).getByRole('button', { name: 'Remove' }).click()
  const confirm = page.getByRole('alertdialog', { name: 'Remove agent-names?' })
  await expect(confirm.getByRole('list', { name: 'Tasks that lose it' })).toHaveCount(0)
})

test('removing a question from inside a Consumer sheet returns to the Consumer', async ({ page }) => {
  await page.goto('/ui/kg/support/use-case?tab=consumers')

  const sheet = await openConsumer(page, 'Triage bot')
  await expandTask(sheet, 'Route a new ticket to an agent')
  await sheet.getByRole('button', { name: /^What are our agents called\?/ }).click()
  await page.getByRole('dialog', { name: 'What are our agents called?' }).getByRole('button', { name: 'Remove' }).click()
  await page.getByRole('alertdialog', { name: 'Remove agent-names?' }).getByRole('button', { name: 'Remove' }).click()

  const back = page.getByRole('dialog', { name: 'Triage bot' })
  await expect(back).toBeVisible()
  const route = await expandTask(back, 'Route a new ticket to an agent')
  await expect(
    route.getByRole('list', { name: 'Competency Questions route-ticket needs' }).getByRole('listitem'),
  ).toHaveText([/What are our customers called\?/])
})

test.describe('with Consumer Gates declared in use-case.yaml', () => {
  test.use({ seed: 'plant_consumer_gates' })

  test('editing a Consumer keeps its Consumer Gates and its verdict', async ({ page }) => {
    await page.goto('/ui/kg/plant/use-case?tab=consumers')

    const sheet = await openConsumer(page, 'Reliability dashboard')
    await sheet.getByRole('button', { name: 'Edit', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Edit Consumer reliability-dashboard' })
    await dialog.getByRole('textbox', { name: 'Name' }).fill('Breakdown dashboard')
    await dialog.getByRole('button', { name: 'Save' }).click()

    const gate = page.getByRole('dialog', { name: 'Breakdown dashboard' }).getByRole('region', { name: 'Consumer Gate' })
    await expect(gate.getByRole('list', { name: 'Declared Consumer Gates' })).toContainText('triage-rows-hold')
    await expect(gate.getByRole('group', { name: 'Latest verdict' })).toContainText('Failed')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('status')).toHaveText('Saved as Use Case Version 3.')
    await expect(tile(page, 'Breakdown dashboard')).toContainText('Consumer Gate failed')
  })
})

test.describe('signed in with a read-only API Token', () => {
  test.use({ mode: 'server', seed: 'support_use_case_consumers_reader' })

  test('every Consumer and Task edit control is disabled', async ({ page, stetiq }) => {
    await signIn(page, (stetiq.seeded.grace as { value: string }).value)
    await page.goto('/ui/kg/support/use-case?tab=consumers')
    await expect(page.getByRole('button', { name: 'Add Consumer' })).toBeDisabled()
    await page.getByRole('button', { name: 'Add Consumer' }).hover({ force: true })
    await expect(page.getByRole('tooltip')).toHaveText('Needs edit access')

    const sheet = await openConsumer(page, 'Triage bot')
    for (const name of ['Edit', 'Remove', 'Add Task', 'Edit Task route-ticket', 'Remove Task route-ticket']) {
      await expect(sheet.getByRole('button', { name, exact: true })).toBeDisabled()
    }
  })
})
