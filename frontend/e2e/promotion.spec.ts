import { expect, signIn, test } from './fixtures'

test.describe('as a reader (stetiq server)', () => {
  test.use({ mode: 'server', seed: 'support_lineage_reader' })

  test('Promote is disabled with a tooltip, and the server still refuses the write', async ({
    page,
    stetiq,
  }) => {
    await signIn(page, (stetiq.seeded.grace as { value: string }).value)
    await page.goto('/ui/kg/support/versions/3')
    const promote = page.getByRole('button', { name: 'Promote' })
    await expect(promote).toBeDisabled()
    await promote.hover({ force: true })
    await expect(page.getByRole('tooltip')).toHaveText('Needs edit access')

    // The disabled button is only a hint: the same request the dialog sends is refused.
    const csrf = (await page.context().cookies()).find((c) => c.name === 'stetiq_csrf')
    const response = await page.request.put('/api/v1/knowledge-graphs/support/aliases/staging', {
      data: { version: 3 },
      headers: { 'X-CSRF-Token': csrf?.value ?? '' },
    })
    expect(response.status()).toBe(403)
    expect((await response.json()).error.type).toBe('PermissionDeniedError')

    await page.getByRole('link', { name: 'Promotions' }).click()
    const rows = page.getByRole('table', { name: 'Promotions' }).getByRole('row')
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(1)).toHaveText(/staging.*—.*v2/)
  })
})

test.describe('as an editor (stetiq ui)', () => {
  test.use({ seed: 'support_lineage' })

  test('promoting to a new Alias creates it, and the Promotions page audits it with the actor and Gate result', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/2')
    await page.getByRole('button', { name: 'Promote' }).click()
    const dialog = page.getByRole('dialog', { name: 'Promote v2' })

    await dialog.getByRole('radio', { name: 'New Alias' }).check()
    await dialog.getByRole('textbox', { name: 'New Alias name' }).fill('canary')
    await expect(dialog.getByText('canary does not exist yet')).toBeVisible()
    await dialog.getByRole('button', { name: 'Promote to canary' }).click()

    await expect(dialog).toBeHidden()
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('v2')
    await expect(page.getByText('canary', { exact: true })).toBeVisible()

    await page.getByRole('link', { name: 'Promotions' }).click()
    await expect(page).toHaveURL('/ui/kg/support/promotions')
    const rows = page.getByRole('table', { name: 'Promotions' }).getByRole('row')
    // Newest first: canary (now), staging → v2 (seed), production → v1 (creation).
    await expect(rows).toHaveCount(4)
    await expect(rows.nth(1)).toHaveText(/canary.*—.*v2.*e2e.*Passed/)
    await expect(rows.nth(2)).toHaveText(/staging.*—.*v2/)
  })
})

test.describe('the Promote dialog (stetiq ui)', () => {
  test.use({ seed: 'support_breaking_change' })

  test('shows the Ontology Diff against the Alias’s current version, breaking changes first, and the latest Gate result', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/4')
    await page.getByRole('button', { name: 'Promote' }).click()
    const dialog = page.getByRole('dialog', { name: 'Promote v4' })
    const gate = dialog.getByRole('region', { name: 'Latest Gate result' })
    await expect(gate).toContainText('None')
    await expect(gate).toContainText('never block')

    await dialog.getByRole('radio', { name: 'staging' }).check()
    const diff = dialog.getByRole('region', { name: 'Ontology Diff' })
    await expect(diff.getByText('Changes from v2 (staging) to v4')).toBeVisible()
    await expect(diff.getByText('Overall: breaking')).toBeVisible()
    const rows = diff.getByRole('table', { name: 'Changes' }).getByRole('row')
    await expect(rows.nth(1)).toHaveText(/breaking.*removed.*Ticket\.opened_at/)
    // A failed or missing Gate result never blocks the Promotion.
    await expect(dialog.getByRole('button', { name: 'Promote to staging' })).toBeEnabled()

    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await page.goto('/ui/kg/support/versions/2')
    await page.getByRole('button', { name: 'Promote' }).click()
    const v2 = page.getByRole('dialog', { name: 'Promote v2' })
    await expect(v2.getByRole('region', { name: 'Latest Gate result' })).toContainText('Passed')
    await v2.getByRole('radio', { name: 'staging' }).check()
    await expect(v2.getByText('staging already points to v2.')).toBeVisible()
    await expect(v2.getByRole('button', { name: 'Promote to staging' })).toBeDisabled()
  })

  test('promoting to the Contract Alias needs an extra confirmation that Construction Runs and Drift switch', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions/2')
    await page.getByRole('button', { name: 'Promote' }).click()
    const dialog = page.getByRole('dialog', { name: 'Promote v2' })
    await dialog.getByRole('radio', { name: 'production' }).check()
    await expect(
      dialog.getByRole('region', { name: 'Ontology Diff' }).getByText('Overall: additive'),
    ).toBeVisible()

    const promote = dialog.getByRole('button', { name: 'Promote to production' })
    await expect(dialog.getByText('production is the Contract Alias')).toBeVisible()
    await expect(dialog.getByText(/Construction Runs will declare v2.*Drift/)).toBeVisible()
    await expect(promote).toBeDisabled()
    await dialog.getByRole('checkbox', { name: 'Switch Construction Runs and Drift to v2' }).check()
    await promote.click()

    await expect(dialog).toBeHidden()
    await page.getByRole('link', { name: 'Promotions' }).click()
    const rows = page.getByRole('table', { name: 'Promotions' }).getByRole('row')
    await expect(rows.nth(1)).toHaveText(/production.*v1.*v2.*e2e.*Passed/)
  })
})
