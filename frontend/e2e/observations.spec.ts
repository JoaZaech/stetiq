import { expect, test } from './fixtures'

test.describe('with Drift', () => {
  test.use({ seed: 'observed_support' })

  test('Observations are a table, newest first, each with its status, time, source and findings', async ({
    page,
    stetiq,
  }) => {
    await page.goto('/ui/kg/support/observations')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('Observations')

    const rows = page.getByRole('table', { name: 'Observations' }).getByRole('row')
    await expect(rows).toHaveCount(3)
    const [onDemand, fromRun] = [rows.nth(1), rows.nth(2)]
    await expect(onDemand.getByRole('cell')).toHaveText([/\d/, 'Drift', 'on demand', 'v1', '4'])
    await expect(onDemand.locator('time')).toHaveAttribute('datetime', /^\d{4}-\d{2}-\d{2}T/)
    const runId = stetiq.seeded.run_id as string
    await expect(fromRun.getByRole('cell')).toHaveText([/\d/, 'No Drift', `run ${runId.slice(0, 8)}`, '—', '—'])
    await expect(fromRun.getByRole('link', { name: `Run ${runId.slice(0, 8)}` })).toHaveAttribute(
      'href',
      `/ui/kg/support/runs/${runId}`,
    )
    await expect(page.getByText('2 Observations')).toBeVisible()
  })

  test('the search and the Status filter narrow the table, and stay in the URL', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    const rows = page.getByRole('table', { name: 'Observations' }).getByRole('row')

    await page.getByRole('button', { name: 'Status: All' }).click()
    await page.getByRole('menuitemradio', { name: /^No Drift/ }).click()
    await expect(rows).toHaveCount(2)
    await expect(page).toHaveURL(/status=No\+Drift/)
    await expect(page.getByText('1 of 2 Observations')).toBeVisible()

    await page.goto('/ui/kg/support/observations?q=production')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(1)).toContainText('Drift')
  })

  test('a row opens a sheet with the four evaluation tiles and the findings table', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    await page.getByRole('table', { name: 'Observations' }).getByRole('row').nth(1).click()

    const sheet = page.getByRole('dialog')
    await expect(page).toHaveURL(/sheet=observation%3A/)
    await expect(sheet.getByLabel('Contract Alias')).toHaveText('production')
    await expect(sheet.getByRole('link', { name: 'v1' })).toHaveAttribute('href', '/ui/kg/support/versions/1')
    await expect(sheet.getByLabel('Thresholds')).toHaveText('max drop off · max rise 50%')

    const tiles = sheet.getByRole('list', { name: 'Key figures' }).getByRole('listitem')
    await expect(tiles).toHaveText([/^Conformance—$/, /^CQ coverage—$/, /^Gates—$/, /^Drift4findings$/])

    // Concept kinds in the glossary's words: Class, Relation, Attribute.
    const findings = sheet.getByRole('table', { name: 'Findings' }).getByRole('row')
    await expect(findings).toHaveText([
      'ConceptKindFindingChange',
      /^TicketClassCount rose1 → 4 \(\+300%\)$/,
      /^ESCALATEDRelationObserved but not declared$/,
      /^RefundClassObserved but not declared$/,
      /^Ticket\.channelAttributeObserved but not declared$/,
    ])
    await expect(sheet).not.toContainText(/node type|relationship type|property/)
    await expect(sheet).not.toContainText(/Pending Migration|Adopt into a Candidate|Planned/)

    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()
    await expect(page).not.toHaveURL(/sheet=/)
  })
})

test.describe('without Drift', () => {
  test.use({ seed: 'support_lineage' })

  test('an Observation without Drift reads No Drift, with no alert above the table', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    const rows = page.getByRole('table', { name: 'Observations' }).getByRole('row')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(1).getByRole('cell').nth(1)).toHaveText('No Drift')
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})

test.describe('never observed', () => {
  test.use({ seed: 'signed_in_users' })

  test('a Knowledge Graph without Observations says how to trigger one', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')
    await expect(page.getByText('No Observations yet.')).toBeVisible()
    await expect(page.getByText('stetiq observe')).toBeVisible()
  })
})
