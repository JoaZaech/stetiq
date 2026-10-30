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

  const sidebar = page.getByRole('navigation', { name: 'Main' })
  await expect(sidebar.getByRole('button', { name: 'Knowledge Graph: support' })).toHaveText('support')
  for (const name of SECTIONS) {
    await expect(sidebar.getByRole('link', { name })).toHaveAttribute('href', new RegExp(`^/ui/kg/support/`))
  }
  await expect(sidebar.getByRole('link', { name: 'Ontology Versions' })).toHaveAttribute(
    'aria-current',
    'page',
  )

  await sidebar.getByRole('link', { name: 'Promotions' }).click()
  await expect(page).toHaveURL('/ui/kg/support/promotions')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
  await expect(page.getByRole('heading', { level: 2 })).toHaveText('Promotions')
  await expect(sidebar.getByRole('link', { name: 'Back to Knowledge Graphs' })).toHaveCount(0)
})

test.describe('the Knowledge Graph switcher', () => {
  test.use({ seed: 'knowledge_graphs' })

  test('lists every Knowledge Graph with a check on the current one, and switching keeps the section', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/runs')
    const sidebar = page.getByRole('navigation', { name: 'Main' })

    await sidebar.getByRole('button', { name: 'Knowledge Graph: support' }).click()

    const list = page.getByRole('listbox', { name: 'Knowledge Graphs' })
    await expect(list.getByRole('option')).toHaveText(['billing', 'support', 'All Knowledge Graphs'])
    await expect(list.getByRole('option', { name: 'support' })).toHaveAttribute('aria-checked', 'true')
    await expect(list.getByRole('option', { name: 'billing' })).toHaveAttribute('aria-checked', 'false')

    await list.getByRole('option', { name: 'billing' }).click()

    await expect(page).toHaveURL('/ui/kg/billing/runs')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('billing')
    await expect(sidebar.getByRole('button', { name: 'Knowledge Graph: billing' })).toBeVisible()
    await expect(list).toHaveCount(0)
  })

  test('searches by name and switches with the keyboard', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')
    const switcher = page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Knowledge Graph: support' })

    await switcher.focus()
    await page.keyboard.press('Enter')
    await page.getByRole('combobox', { name: 'Search Knowledge Graphs' }).fill('bill')

    const list = page.getByRole('listbox', { name: 'Knowledge Graphs' })
    await expect(list.getByRole('option')).toHaveText(['billing', 'All Knowledge Graphs'])

    await page.keyboard.press('Enter')

    await expect(page).toHaveURL('/ui/kg/billing/use-case')
  })

  test('from a detail or compare page, switching opens that section of the other Knowledge Graph', async ({
    page,
  }) => {
    const sidebar = page.getByRole('navigation', { name: 'Main' })

    await page.goto('/ui/kg/support/versions/2')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('v2')
    await sidebar.getByRole('button', { name: 'Knowledge Graph: support' }).click()
    await page.getByRole('option', { name: 'billing' }).click()
    await expect(page).toHaveURL('/ui/kg/billing/versions')

    await page.goto('/ui/kg/support/versions/compare?id=1&id=2')
    await sidebar.getByRole('button', { name: 'Knowledge Graph: support' }).click()
    await page.getByRole('option', { name: 'billing' }).click()
    await expect(page).toHaveURL('/ui/kg/billing/versions')
  })

  test('the switcher stays highlighted while its list is open, expanded or collapsed to an icon', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions')
    const sidebar = page.getByRole('navigation', { name: 'Main' })
    const switcher = sidebar.getByRole('button', { name: 'Knowledge Graph: support' })
    const background = () => switcher.evaluate((el) => getComputedStyle(el).backgroundColor)

    for (const collapsed of [false, true]) {
      if (collapsed) {
        await page.getByRole('button', { name: 'Toggle Sidebar' }).first().click()
        await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThan(64)
      }
      await page.mouse.move(0, 0)
      const closed = await background()

      // By keyboard, so no hover style is in play; focus also opens the collapsed tooltip.
      await switcher.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('listbox', { name: 'Knowledge Graphs' })).toBeVisible()
      await expect.poll(background).not.toBe(closed)

      await page.keyboard.press('Escape')
      await expect(page.getByRole('listbox', { name: 'Knowledge Graphs' })).toHaveCount(0)
      await switcher.blur()
      await expect.poll(background).toBe(closed)
    }
  })

  test('"All Knowledge Graphs" opens the list page', async ({ page }) => {
    await page.goto('/ui/settings')

    await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Select a Knowledge Graph' }).click()
    await page.getByRole('option', { name: 'All Knowledge Graphs' }).click()

    await expect(page).toHaveURL('/ui/kg')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Knowledge Graphs')
  })
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
  await page.getByRole('radio', { name: 'Table' }).click()

  const classes = page.getByRole('table', { name: 'Classes' })
  const relations = page.getByRole('table', { name: 'Relations' })
  const attributes = page.getByRole('table', { name: 'Attributes' })
  await expect(classes.getByRole('row')).toHaveText([
    /Class.*Superclass.*Attributes.*Outgoing.*Incoming.*Constraints.*Description/,
    /^Party\s*—\s*1\s*—/,
    /^Agent\s*Party\s*0\s*\(1\)/,
    /^Customer\s*Party\s*0\s*\(1\)\s*OPENED → Ticket\s*—\s*UNIQUENESS \(name\)\s*Someone who opens tickets/,
    /^Ticket\s*—\s*2\s*—\s*OPENED ← Customer/,
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
  await expect(relations.getByRole('row')).toHaveText([/Relation/, /^No relations match\.$/])
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
