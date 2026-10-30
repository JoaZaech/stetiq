import { expect, test } from './fixtures'

test('Home welcomes the user at /, with a "Home" breadcrumb', async ({ page }) => {
  await page.goto('/ui/')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome to stetiq')
  await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText('Home')
  await expect(page).toHaveTitle('Home · stetiq')
})

const GUIDE_CARDS = [
  ['Declare an Ontology', '/ui/help/concepts#knowledge-graphs-and-ontology-versions'],
  ['Construction Runs', '/ui/help/concepts#construction-runs-and-conformance'],
  ['Use Cases & Evaluation', '/ui/help/concepts#evaluators-and-use-cases'],
  ['Observations & Drift', '/ui/help/concepts#observation-and-drift'],
  ['Promotions & Aliases', '/ui/help/concepts#aliases-and-promotion'],
] as const

test('Getting Started has five cards, each opening its user-guide page', async ({ page }) => {
  await page.goto('/ui/')
  const gettingStarted = page.getByRole('region', { name: 'Getting Started' })

  const cards = gettingStarted.getByRole('link')
  await expect(cards).toHaveCount(GUIDE_CARDS.length)
  for (const [i, [name, href]] of GUIDE_CARDS.entries()) {
    await expect(cards.nth(i).getByRole('heading')).toHaveText(name)
    await expect(cards.nth(i)).toHaveAttribute('href', href)
  }

  await cards.nth(1).click()

  await expect(page).toHaveURL('/ui/help/concepts#construction-runs-and-conformance')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Concepts')
})

test('Getting Started stays collapsed after a reload', async ({ page }) => {
  await page.goto('/ui/')
  const toggle = page.getByRole('button', { name: 'Getting Started' })
  const cards = page.getByRole('region', { name: 'Getting Started' }).getByRole('link')
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  await expect(cards.first()).toBeVisible()

  await toggle.click()

  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(cards).toHaveCount(0)

  await page.reload()

  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect(cards).toHaveCount(0)

  await toggle.click()

  await expect(cards).toHaveCount(GUIDE_CARDS.length)
})
