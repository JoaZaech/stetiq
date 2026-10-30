import { expect, signIn, test } from './fixtures'

test.use({ seed: 'support_lineage' })

const SECTIONS = ['Ontology Versions', 'Construction Runs', 'Use Case', 'Observations', 'Promotions']

test('a Knowledge Graph shows its sections in the sidebar and its header', async ({ page }) => {
  await page.goto('/ui/kg/support')

  await expect(page).toHaveURL('/ui/kg/support/versions')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
  const header = page.getByRole('region', { name: 'Knowledge Graph' })
  await expect(header.getByText('Evolution Mode')).toBeVisible()
  await expect(header.getByText('evolving')).toBeVisible()
  await expect(header.getByText('Contract Alias')).toBeVisible()
  await expect(header.getByText('production → v1')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
    /Knowledge Graphs.*support.*Ontology Versions/,
  )

  const sections = page.getByRole('navigation', { name: 'Knowledge Graph' })
  for (const name of SECTIONS) await expect(sections.getByRole('link', { name })).toBeVisible()
  await expect(sections.getByRole('link', { name: 'Ontology Versions' })).toHaveAttribute(
    'aria-current',
    'page',
  )

  await sections.getByRole('link', { name: 'Promotions' }).click()
  await expect(page).toHaveURL('/ui/kg/support/promotions')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
  await expect(page.getByRole('heading', { level: 2 })).toHaveText('Promotions')

  await page.getByRole('link', { name: 'Back to Knowledge Graphs' }).click()
  await expect(page).toHaveURL('/ui/kg')
  await expect(page.getByRole('navigation', { name: 'Knowledge Graph' })).toHaveCount(0)
})

test('the Ontology Version table lists versions newest first with Alias chips and a Candidate badge', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions')
  const table = page.getByRole('table', { name: 'Ontology Versions' })
  const rows = table.getByRole('row')

  await expect(rows.first()).toHaveText(/Version.*Origin.*Created.*Aliases/)
  await expect(rows).toHaveCount(4)
  await expect(rows.nth(1)).toHaveText(/v3.*run.*Candidate/)
  await expect(rows.nth(2)).toHaveText(/v2.*registered.*staging/)
  await expect(rows.nth(3)).toHaveText(/v1.*registered.*production/)
  await expect(rows.nth(2)).not.toHaveText(/Candidate/)
  await expect(rows.nth(3).getByText('production')).toHaveAccessibleDescription('Contract Alias')
  await expect(rows.nth(2).getByText('staging')).not.toHaveAccessibleDescription('Contract Alias')

  await rows.nth(2).getByRole('link', { name: 'v2' }).click()
  await expect(page).toHaveURL('/ui/kg/support/versions/2')
})

test('the version Overview shows its metadata, Evaluator results and latest Gate result', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/ui/kg/support/versions/2')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('v2')
  await expect(page.getByRole('main').getByText('staging')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
    /Knowledge Graphs.*support.*Ontology Versions.*v2/,
  )
  await expect(page.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')

  const details = page.getByRole('region', { name: 'Details' })
  await expect(details).toContainText(/Number\s*2/)
  await expect(details).toContainText(/Origin\s*registered/)
  await expect(details).toContainText(/Content hash\s*[0-9a-f]{12}/)
  await details.getByRole('button', { name: 'Copy content hash' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^[0-9a-f]{64}$/)
  await expect(details).not.toContainText('Construction Run')

  const results = page.getByRole('table', { name: 'Evaluator results' })
  await expect(results.getByRole('row').first()).toHaveText(/Evaluator.*Metric.*Value.*Use Case Version/)
  await expect(
    results.getByRole('row').filter({ hasText: 'structural_answerability' }).filter({ hasText: 'answerable_ratio' }),
  ).toHaveText(/answerable_ratio\s*1\s*1$/)
  await expect(results.getByRole('row').filter({ hasText: 'max_depth' })).toHaveText(/hierarchy.*max_depth\s*2/)

  await expect(page.getByRole('region', { name: 'Latest Gate result' })).toContainText('Passed')
})

test('a run-originated version links its Construction Run; an ungated version has no Gate result', async ({
  page,
  stetiq,
}) => {
  await page.goto('/ui/kg/support/versions/3')

  const details = page.getByRole('region', { name: 'Details' })
  await expect(details).toContainText(/Origin\s*run/)
  await expect(details.getByRole('link', { name: String(stetiq.seeded.run_id) })).toHaveAttribute(
    'href',
    `/ui/kg/support/runs/${String(stetiq.seeded.run_id)}`,
  )
  await expect(page.getByRole('region', { name: 'Latest Gate result' })).toContainText('None')
})

test('the Ontology tab lists Concepts grouped, with hierarchy and constraints, and searchable', async ({
  page,
}) => {
  await page.goto('/ui/kg/support/versions/3')
  await page.getByRole('navigation', { name: 'Ontology Version' }).getByRole('link', { name: 'Ontology' }).click()
  await expect(page).toHaveURL('/ui/kg/support/versions/3/ontology')

  const classes = page.getByRole('table', { name: 'Classes' })
  const relations = page.getByRole('table', { name: 'Relations' })
  const attributes = page.getByRole('table', { name: 'Attributes' })
  await expect(classes.getByRole('row')).toHaveText([
    /Class.*Superclass.*Constraints/,
    /^Party/,
    /^Agent\s*Party/,
    /^Customer\s*Someone who opens tickets\s*Party\s*UNIQUENESS \(name\)/,
    /^Ticket/,
  ])
  await expect(relations.getByRole('row').nth(1)).toHaveText(/OPENED.*\(Customer\)-\[OPENED\]->\(Ticket\)/)
  await expect(attributes.getByRole('row')).toHaveText([
    /Class or relation.*Attribute.*Type.*Required/,
    /Party\s*name\s*STRING\s*Required/,
    /Ticket\s*opened_at\s*DATE/,
    /Ticket\s*priority\s*INTEGER/,
  ])

  await page.getByRole('searchbox', { name: 'Search Concepts' }).fill('ticket')

  await expect(classes.getByRole('row')).toHaveText([/Class/, /^Customer/, /^Ticket/])
  await expect(relations).toHaveCount(0)
  await expect(page.getByText('No relations match “ticket”.')).toBeVisible()
  await expect(attributes.getByRole('row')).toHaveCount(3)
})

test('an unknown Knowledge Graph or version shows a not-found page', async ({ page }) => {
  await page.goto('/ui/kg/nope/versions')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graph not found')

  await page.goto('/ui/kg/support/versions/9')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ontology Version not found')

  await page.goto('/ui/kg/support/versions/latest/ontology')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ontology Version not found')

  await page.goto('/ui/kg/support/no-such-section')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found')
})

test.describe('with a token that can read only `support`', () => {
  test.use({ mode: 'server', seed: 'support_lineage_reader' })

  test('a Knowledge Graph outside the grants shows the same not-found page as an unknown one', async ({
    page,
    stetiq,
  }) => {
    await signIn(page, (stetiq.seeded.grace as { value: string }).value)

    await page.goto('/ui/kg/support/versions/2')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('v2')

    await page.goto('/ui/kg/secret/versions')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graph not found')
    await expect(page.getByText(/permission/i)).toHaveCount(0)
    await page.goto('/ui/kg/secret/versions/1')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graph not found')
  })
})
