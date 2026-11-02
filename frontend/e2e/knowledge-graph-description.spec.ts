import { expect, signIn, test } from './fixtures'

test.use({ mode: 'server', seed: 'described_support' })

const token = (seeded: Record<string, unknown>, user: string) =>
  (seeded[user] as { value: string }).value

test('an editor edits the description in a markdown editor and sees it rendered', async ({
  page,
  stetiq,
}) => {
  await signIn(page, token(stetiq.seeded, 'ada'))
  await page.goto('/ui/kg/support')
  const about = page.getByRole('region', { name: 'About' })
  // The Overview shows the first sentence; the rest is behind More.
  await expect(about).toContainText('Answers support questions.')
  await expect(about.getByRole('listitem')).toHaveCount(0)
  await about.getByRole('button', { name: 'More' }).click()
  await expect(about.getByRole('listitem')).toHaveText(['triage', 'escalation'])

  await about.getByRole('button', { name: 'Edit description' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit description' })
  const editor = dialog.getByRole('textbox', { name: 'Description' })
  await expect(editor).toHaveValue('Answers **support** questions.\n\n- triage\n- escalation')
  await editor.fill('Routes tickets to [agents](https://example.com/agents).')
  await dialog.getByRole('tab', { name: 'Preview' }).click()
  await expect(dialog.getByRole('link', { name: 'agents' })).toBeVisible()

  // The write is authenticated by the sign-in cookie, so it must carry the CSRF header.
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith('/knowledge-graphs/support/description') && r.request().method() === 'PUT',
  )
  await dialog.getByRole('button', { name: 'Save' }).click()
  const response = await saved
  expect(response.status()).toBe(200)
  expect(await response.request().headerValue('x-csrf-token')).toBeTruthy()

  await expect(dialog).toBeHidden()
  await expect(about.getByRole('link', { name: 'agents' })).toHaveAttribute(
    'href',
    'https://example.com/agents',
  )
  await expect(about.getByRole('listitem')).toHaveCount(0)
  await page.reload()
  await expect(about.getByRole('link', { name: 'agents' })).toBeVisible()
})

test("a section page's one-line header edits the description, which shows only on the Overview", async ({
  page,
  stetiq,
}) => {
  await signIn(page, token(stetiq.seeded, 'ada'))
  await page.goto('/ui/kg/support/runs')
  const header = page.getByRole('region', { name: 'Knowledge Graph' })
  await expect(header.getByRole('heading', { level: 1 })).toHaveText('support')
  await expect(page.getByText('triage', { exact: true })).toHaveCount(0)

  await header.getByRole('button', { name: 'Edit description' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit description' })
  await dialog.getByRole('textbox', { name: 'Description' }).fill('Routes **tickets**.')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText('Routes tickets.')).toHaveCount(0)

  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Overview' }).click()
  await expect(page.getByRole('region', { name: 'About' })).toContainText('Routes tickets.')
})

test('a reader sees the rendered description but Edit is disabled for lack of edit access, on the Overview and in the header', async ({
  page,
  stetiq,
}) => {
  await signIn(page, token(stetiq.seeded, 'grace'))
  await page.goto('/ui/kg/support')
  const about = page.getByRole('region', { name: 'About' })

  await about.getByRole('button', { name: 'More' }).click()
  await expect(about.getByRole('listitem')).toHaveText(['triage', 'escalation'])
  for (const scope of [about, page.getByRole('region', { name: 'Knowledge Graph' })]) {
    if (scope !== about) await page.goto('/ui/kg/support/versions')
    const edit = scope.getByRole('button', { name: 'Edit description' })
    await expect(edit).toBeDisabled()
    await edit.hover({ force: true })
    await expect(page.getByRole('tooltip')).toHaveText('Needs edit access')
  }
})
