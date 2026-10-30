import { expect, signIn, stetiqCli, test } from './fixtures'

interface IssuedToken {
  id: string
  value: string
}

test.use({ mode: 'server', seed: 'signed_in_users' })

const adaToken = (seeded: Record<string, unknown>) => seeded.ada as IssuedToken

test('signing in with an API Token keeps it in an HttpOnly, SameSite=Strict cookie', async ({
  page,
  context,
  stetiq,
}) => {
  await page.goto('/ui/sign-in')
  await page.getByLabel('API Token').fill(adaToken(stetiq.seeded).value)
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('heading', { level: 1, name: 'Knowledge Graphs' })).toBeVisible()
  const token = (await context.cookies()).find((c) => c.name === 'stetiq_token')
  expect(token).toMatchObject({ httpOnly: true, sameSite: 'Strict', path: '/' })
})

test('an invalid token is refused with a message', async ({ page }) => {
  await page.goto('/ui/sign-in')
  await page.getByLabel('API Token').fill('stq_nope_nope')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('alert')).toContainText('Invalid or revoked API token')
  await expect(page).toHaveURL(/\/ui\/sign-in/)
})

test('a page opened before signing in asks for a token, then comes back', async ({
  page,
  stetiq,
}) => {
  await page.goto('/ui/settings')

  await expect(page).toHaveURL(/\/ui\/sign-in/)
  await page.getByLabel('API Token').fill(adaToken(stetiq.seeded).value)
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/ui\/settings$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
})

test('Settings shows who is signed in and what they may read or edit', async ({
  page,
  stetiq,
}) => {
  await signIn(page, adaToken(stetiq.seeded).value)
  await page.goto('/ui/settings')

  const access = page.getByRole('region', { name: 'Access' })
  await expect(access).toContainText('Signed in as ada')
  const grants = access.getByRole('table', { name: 'Grants' })
  await expect(grants.getByRole('row', { name: 'support edit' })).toBeVisible()
  await expect(grants.getByRole('row', { name: 'billing read' })).toBeVisible()
})

test('signing out forgets the token', async ({ page, context, stetiq }) => {
  await signIn(page, adaToken(stetiq.seeded).value)
  await page.goto('/ui/settings')

  await page.getByRole('button', { name: 'Sign out' }).click()

  await expect(page).toHaveURL(/\/ui\/sign-in/)
  expect((await context.cookies()).map((c) => c.name)).not.toContain('stetiq_token')
  await page.goto('/ui/settings')
  await expect(page).toHaveURL(/\/ui\/sign-in/)
})

test('a revoked token sends the user back to sign-in', async ({ page, stetiq }) => {
  const token = adaToken(stetiq.seeded)
  await signIn(page, token.value)

  stetiqCli('token', 'revoke', token.id, '--database-url', stetiq.trackingUri)
  await page.goto('/ui/settings')

  await expect(page).toHaveURL(/\/ui\/sign-in/)
  await expect(page.getByLabel('API Token')).toBeVisible()
})
