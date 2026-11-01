import { expect, signIn, test } from './fixtures'
import type { Page } from '@playwright/test'

// support_lineage: Use Case Version 1 asks `customer-names` (concepts Customer.name).
test.use({ seed: 'support_lineage' })

const latestVersion = (page: Page) =>
  page.getByRole('region', { name: /^Use Case Version \d+$/ })

const questionItems = (page: Page, version: number) =>
  page
    .getByRole('region', { name: `Use Case Version ${version}` })
    .getByRole('list', { name: 'Competency Questions' })
    .getByRole('listitem')

/** Opens a question's sheet from its row in the Competency Questions list. */
const openQuestion = async (page: Page, question: string) => {
  await page.getByRole('button', { name: new RegExp(`^${question.replace(/[?.]/g, '\\$&')}`) }).click()
  const sheet = page.getByRole('dialog', { name: question })
  await expect(sheet).toBeVisible()
  return sheet
}

test('an editor adds a Competency Question, which creates a new Use Case Version', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/use-case')
  await expect(latestVersion(page)).toHaveAccessibleName('Use Case Version 1')

  await page.getByRole('button', { name: 'Add Competency Question' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Competency Question' })
  await dialog.getByRole('textbox', { name: 'Id' }).fill('ticket-dates')
  await dialog.getByRole('textbox', { name: 'Question' }).fill('When was each ticket opened?')
  await dialog.getByRole('textbox', { name: 'Cypher query' }).fill('MATCH (t:Ticket) RETURN t.opened_at')
  await dialog.getByRole('textbox', { name: 'Expected answer' }).fill('[{"opened_at": "2026-01-01"}]')
  await dialog.getByRole('textbox', { name: 'Concept mapping' }).fill('Ticket.opened_at')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(dialog).toBeHidden()
  await expect(questionItems(page, 2)).toHaveText([/What are our customers called\?/, /When was each ticket opened\?/])
  await expect(page.getByRole('status')).toHaveText(/Saved as Use Case Version 2/)

  const sheet = await openQuestion(page, 'When was each ticket opened?')
  await expect(sheet.getByRole('region', { name: 'Author details' })).toHaveText(
    /ticket-dates.*MATCH \(t:Ticket\) RETURN t\.opened_at.*"opened_at": "2026-01-01".*Ticket\.opened_at/s,
  )
  await page.keyboard.press('Escape')
  await page.reload()
  await expect(page.getByRole('table', { name: 'Use Case Versions' }).getByRole('row')).toHaveCount(3)
})

test('after saving, the list shows the new version’s answerability', async ({ page }) => {
  // The server judges it while registering the version: the page only reads the result.
  const writes: string[] = []
  page.on('request', (r) => {
    if (r.method() !== 'GET') writes.push(new URL(r.url()).pathname)
  })
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Add Competency Question' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Competency Question' })
  await dialog.getByRole('textbox', { name: 'Id' }).fill('refunds')
  await dialog.getByRole('textbox', { name: 'Question' }).fill('Which tickets were refunded?')
  await dialog.getByRole('textbox', { name: 'Concept mapping' }).fill('Refund')
  await dialog.getByRole('button', { name: 'Save' }).click()

  // The latest Ontology Version is v3 (the Candidate), which has Customer.name but no Refund.
  const latest = page.getByRole('region', { name: 'Use Case Version 2' })
  await expect(latest).toContainText('Ontology Version v3 answers 1 of 2 Competency Questions.')
  await expect(questionItems(page, 2)).toHaveText([
    /What are our customers called\?.*Answerable/,
    /Which tickets were refunded\?.*Unanswerable/,
  ])
  expect(writes).toEqual(['/api/v1/knowledge-graphs/support/use-case-versions'])

  const sheet = await openQuestion(page, 'Which tickets were refunded?')
  await expect(sheet).toContainText('Unanswerable on Ontology Version v3')
  await expect(sheet.getByRole('region', { name: 'Missing Concepts' }).getByRole('listitem')).toHaveText(['Refund'])

  await page.keyboard.press('Escape')
  await page.reload()
  await expect(latest).toContainText('answers 1 of 2 Competency Questions.')
})

test.describe('with answerability of every kind', () => {
  // support_task_readiness: on v3, customer-names and agent-names are answerable,
  // refund-amounts is unanswerable, satisfaction is unmapped; the Triage bot's route-ticket
  // needs those four, and ticket-count serves no Task.
  test.use({ seed: 'support_task_readiness' })

  test('an unmapped question reads as Can’t check, which explains itself', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const satisfaction = questionItems(page, 2).filter({ hasText: 'How satisfied is each customer?' })
    await expect(satisfaction).toContainText("Can't check")
    await satisfaction.getByText("Can't check").hover()
    await expect(page.getByRole('tooltip')).toHaveText("No Concept mapping or query, so stetiq can't tell")
  })

  test('the sheet names the Consumer and Task that need the question', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openQuestion(page, 'How much was refunded per ticket?')
    await expect(sheet).toContainText('Unanswerable on Ontology Version v3')
    // The whole class is missing, so that is what it names.
    await expect(sheet.getByRole('region', { name: 'Missing Concepts' }).getByRole('listitem')).toHaveText([
      'Refund',
    ])
    await expect(sheet.getByRole('region', { name: 'Needed by' }).getByRole('listitem')).toHaveText([
      'Triage bot · Route a new ticket to an agent',
    ])
  })
})

test.describe('with three Use Case Versions', () => {
  // v3 asks customer-names and ticket-dates.
  test.use({ seed: 'support_use_case_versions' })

  test('an editor edits a question from its sheet, whose id is read-only, into a new Use Case Version', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openQuestion(page, 'What is each customer called?')
    await sheet.getByRole('button', { name: 'Edit' }).click()
    const dialog = page.getByRole('dialog', { name: 'Edit customer-names' })
    const id = dialog.getByRole('textbox', { name: 'Id' })
    await expect(id).toHaveValue('customer-names')
    await expect(id).not.toBeEditable()
    await expect(dialog.getByRole('textbox', { name: 'Concept mapping' })).toHaveValue('Customer.name')
    await dialog.getByRole('textbox', { name: 'Question' }).fill('What is every customer called?')
    await dialog.getByRole('button', { name: 'Save' }).click()

    await expect(dialog).toBeHidden()
    const edited = page.getByRole('dialog', { name: 'What is every customer called?' })
    await expect(edited).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(edited).toBeHidden()
    await expect(questionItems(page, 4)).toHaveText([/What is every customer called\?/, /When was each ticket opened\?/])
  })

  test('an editor removes a question from its sheet after confirming, creating a new Use Case Version', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openQuestion(page, 'When was each ticket opened?')
    await sheet.getByRole('button', { name: 'Remove' }).click()
    const confirm = page.getByRole('alertdialog', { name: 'Remove ticket-dates?' })
    await confirm.getByRole('button', { name: 'Cancel' }).click()
    await expect(sheet).toBeVisible()

    await sheet.getByRole('button', { name: 'Remove' }).click()
    await confirm.getByRole('button', { name: 'Remove' }).click()

    await expect(confirm).toBeHidden()
    await expect(sheet).toBeHidden()
    await expect(page).toHaveURL(/\/ui\/kg\/support\/use-case$/)
    await expect(questionItems(page, 4)).toHaveText([/What is each customer called\?/])
    await expect(page.getByRole('status')).toHaveText(/Saved as Use Case Version 4/)
  })

  test('saving unchanged content creates no new version and says so', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openQuestion(page, 'When was each ticket opened?')
    await sheet.getByRole('button', { name: 'Edit' }).click()
    const dialog = page.getByRole('dialog', { name: 'Edit ticket-dates' })
    await dialog.getByRole('button', { name: 'Save' }).click()
    await expect(dialog).toBeHidden()
    await page.keyboard.press('Escape')

    await expect(page.getByRole('status')).toHaveText(
      'Nothing changed: Use Case Version 3 already has this content, so no new version was created.',
    )
    await expect(page.getByRole('table', { name: 'Use Case Versions' }).getByRole('row')).toHaveCount(4)
  })
})

test.describe('signed in with an API Token', () => {
  // described_support: ada can edit `support`, grace can only read it.
  test.use({ mode: 'server', seed: 'described_support' })

  const token = (seeded: Record<string, unknown>, user: string) =>
    (seeded[user] as { value: string }).value

  test('an editor saves through the sign-in cookie, with the CSRF header', async ({ page, stetiq }) => {
    await signIn(page, token(stetiq.seeded, 'ada'))
    await page.goto('/ui/kg/support/use-case')

    const sheet = await openQuestion(page, 'What are our customers called?')
    await sheet.getByRole('button', { name: 'Edit' }).click()
    const dialog = page.getByRole('dialog', { name: 'Edit customer-names' })
    await dialog.getByRole('textbox', { name: 'Question' }).fill('Who are our customers?')
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/use-case-versions') && r.request().method() === 'POST',
    )
    await dialog.getByRole('button', { name: 'Save' }).click()
    const response = await saved
    expect(response.status()).toBe(200)
    expect(await response.request().headerValue('x-csrf-token')).toBeTruthy()
    await expect(page.getByRole('dialog', { name: 'Who are our customers?' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('region', { name: 'Use Case Version 2' })).toBeVisible()
  })

  test('a reader sees every edit control disabled, and the server refuses the write', async ({
    page,
    stetiq,
  }) => {
    const grace = token(stetiq.seeded, 'grace')
    await signIn(page, grace)
    await page.goto('/ui/kg/support/use-case')
    await expect(page.getByRole('region', { name: 'Use Case Version 1' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add Competency Question' })).toBeDisabled()

    const sheet = await openQuestion(page, 'What are our customers called?')
    for (const name of ['Edit', 'Remove']) {
      await expect(sheet.getByRole('button', { name })).toBeDisabled()
    }
    await sheet.getByRole('button', { name: 'Remove' }).hover({ force: true })
    await expect(page.getByRole('tooltip')).toHaveText('Needs edit access')

    const refused = await page.request.post('/api/v1/knowledge-graphs/support/use-case-versions', {
      headers: { Authorization: `Bearer ${grace}` },
      data: { use_case: { competency_questions: [{ id: 'x', question: 'Anything?' }] } },
    })
    expect(refused.status()).toBe(403)
    await sheet.getByRole('button', { name: 'Close' }).click()
    await page.reload()
    await expect(page.getByRole('table', { name: 'Use Case Versions' }).getByRole('row')).toHaveCount(2)
  })
})

test('invalid input is shown on its field and nothing is saved', async ({ page }) => {
  const writes: string[] = []
  page.on('request', (r) => {
    if (r.method() !== 'GET') writes.push(r.url())
  })
  await page.goto('/ui/kg/support/use-case')

  await page.getByRole('button', { name: 'Add Competency Question' }).click()
  const dialog = page.getByRole('dialog', { name: 'Add Competency Question' })
  const id = dialog.getByRole('textbox', { name: 'Id' })
  const expected = dialog.getByRole('textbox', { name: 'Expected answer' })
  const concepts = dialog.getByRole('textbox', { name: 'Concept mapping' })
  await id.fill('customer-names')
  await dialog.getByRole('textbox', { name: 'Question' }).fill('Who are our customers?')
  await expected.fill("[{name: 'Ada'}]")
  await concepts.fill('Customer\nCustomer.')
  await dialog.getByRole('button', { name: 'Save' }).click()

  await expect(id).toHaveAttribute('aria-invalid', 'true')
  await expect(id).toHaveAccessibleDescription(
    /The Competency Question customer-names already has this id\./,
  )
  await expect(expected).toHaveAccessibleDescription(/Not valid JSON/)
  await expect(concepts).toHaveAccessibleDescription(/Not a Concept reference: "Customer\."/)
  await expect(dialog).toBeVisible()
  expect(writes).toEqual([])
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('region', { name: 'Use Case Version 1' })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Use Case Versions' }).getByRole('row')).toHaveCount(2)
})
