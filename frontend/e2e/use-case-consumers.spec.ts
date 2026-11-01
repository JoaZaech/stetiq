import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

const consumers = (page: Page) => page.getByRole('region', { name: 'Consumers' })
const tile = (page: Page, name: string) => consumers(page).getByRole('article', { name })

/** Opens a Consumer's sheet from its tile. */
const openConsumer = async (page: Page, name: string) => {
  await tile(page, name).getByRole('button', { name }).click()
  const sheet = page.getByRole('dialog', { name })
  await expect(sheet).toBeVisible()
  return sheet
}

test.describe('with a Use Case that declares Consumers', () => {
  // support_use_case_consumers: the Triage bot (agent, Ada Lovelace) has greet-customer
  // (customer-names) and route-ticket (customer-names, agent-names), both answerable on
  // the latest Ontology Version; the Workload dashboard has only a name and show-agents,
  // which needs no question.
  test.use({ seed: 'support_use_case_consumers' })

  test('a tile shows the kind icon, name, description and readiness, and no id, contact or edit control', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    await expect(consumers(page).getByRole('article')).toHaveCount(2)
    const bot = tile(page, 'Triage bot')
    await expect(bot.getByRole('img', { name: 'agent' })).toBeVisible()
    await expect(bot).toContainText('Routes new tickets to the right team.')
    await expect(bot).toContainText('2 of 2 Tasks ready')
    for (const hidden of ['triage-bot', 'Ada Lovelace', 'Consumer Gate', 'Connector', 'Greet the customer']) {
      await expect(bot).not.toContainText(hidden)
    }
    await expect(bot.getByRole('button')).toHaveCount(1)

    const dashboard = tile(page, 'Workload dashboard')
    await expect(dashboard.getByRole('img', { name: 'Consumer' })).toBeVisible()
    await expect(dashboard).toContainText('1 of 1 Tasks ready')
    await expect(dashboard).not.toContainText('workload-dashboard')
  })

  test('a tile opens the Consumer sheet: kind, id, contact, description, Tasks and Consumer Gate', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openConsumer(page, 'Triage bot')
    await expect(page).toHaveURL(/[?&]sheet=consumer%3Atriage-bot$/)
    await expect(sheet).toContainText('Routes new tickets to the right team.')
    await expect(sheet).toContainText(/Kind\s*agent\s*Id\s*triage-bot\s*Contact\s*Ada Lovelace/)
    const tasks = sheet.getByRole('list', { name: 'Tasks' }).locator(':scope > li')
    await expect(tasks).toHaveCount(2)
    await expect(tasks.nth(0)).toContainText('Greet the customer by name greet-customer')
    await expect(tasks.nth(0).getByRole('img', { name: 'Ready' })).toBeVisible()

    const route = sheet.getByRole('button', { name: /Route a new ticket to an agent/ })
    await expect(route).toHaveAttribute('aria-expanded', 'false')
    const needs = sheet.getByRole('list', { name: 'Competency Questions route-ticket needs' })
    await expect(needs).toBeHidden()
    await route.click()
    await expect(route).toHaveAttribute('aria-expanded', 'true')
    await expect(needs.getByRole('listitem')).toHaveText([
      /What are our agents called\?.*Answerable/,
      /What are our customers called\?.*Answerable/,
    ])

    const gate = sheet.getByRole('region', { name: 'Consumer Gate' })
    await expect(gate).toContainText('No Consumer Gate declared')

    await page.reload()
    await expect(page.getByRole('dialog', { name: 'Triage bot' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(page).not.toHaveURL(/sheet=/)
  })

  test('a question in the Consumer sheet replaces its content, and Back returns to the Consumer', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openConsumer(page, 'Triage bot')
    await sheet.getByRole('button', { name: /Greet the customer by name/ }).click()
    await sheet.getByRole('button', { name: /^What are our customers called\?/ }).click()

    // One sheet, now the question's.
    const question = page.getByRole('dialog', { name: 'What are our customers called?' })
    await expect(question).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(1)
    await expect(page).toHaveURL(/sheet=question%3Acustomer-names&sheet-back=consumer%3Atriage-bot$/)
    await expect(question.getByRole('region', { name: 'Needed by' }).getByRole('listitem')).toHaveCount(2)

    await question.getByRole('button', { name: 'Back' }).click()
    await expect(page.getByRole('dialog', { name: 'Triage bot' })).toBeVisible()
    await expect(page).toHaveURL(/[?&]sheet=consumer%3Atriage-bot$/)

    // Back popped the question's history entry: the browser's Back now closes the sheet.
    await page.goBack()
    await expect(page.getByRole('dialog')).toBeHidden()
  })

  test('the browser’s Back, and Back on a linked question, return to the Consumer sheet', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')
    const sheet = await openConsumer(page, 'Triage bot')
    await sheet.getByRole('button', { name: /Route a new ticket to an agent/ }).click()
    await sheet.getByRole('button', { name: /^What are our agents called\?/ }).click()
    await expect(page.getByRole('dialog', { name: 'What are our agents called?' })).toBeVisible()

    await page.goBack()
    await expect(page.getByRole('dialog', { name: 'Triage bot' })).toBeVisible()

    // A shared link has no history to go back through.
    await page.goto('/ui/kg/support/use-case?sheet=question:agent-names&sheet-back=consumer:triage-bot')
    await page.getByRole('dialog', { name: 'What are our agents called?' }).getByRole('button', { name: 'Back' }).click()
    await expect(page.getByRole('dialog', { name: 'Triage bot' })).toBeVisible()
    await expect(page).toHaveURL(/[?&]sheet=consumer%3Atriage-bot$/)
  })
})

test.describe('with a Use Case without Consumers', () => {
  test.use({ seed: 'support_use_case_versions' })

  test('the Use Case page says no Consumers are declared', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    await expect(consumers(page)).toContainText('No Consumers are declared in this Use Case Version.')
  })
})
