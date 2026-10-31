import type { Locator, Page } from '@playwright/test'
import { expect, test } from './fixtures'

/**
 * The "Planned" placeholders for the downstream vision (docs/vision.md): each is disabled,
 * badged "Planned", explains itself in a tooltip and links to its section of the vision.
 */

/** The placeholder named `name` in `scope`: its disabled stand-in and its "Planned" link. */
function planned(scope: Locator | Page, name: string) {
  return {
    standIn: scope.getByRole('group', { name, exact: true }),
    link: scope.getByRole('link', { name: `Planned: ${name}`, exact: true }),
  }
}

async function expectPlaceholder(scope: Locator | Page, name: string, section: string) {
  const { standIn, link } = planned(scope, name)
  await expect(standIn).toBeVisible()
  await expect(standIn).toBeDisabled()
  await expect(standIn.getByRole('button').and(standIn.locator(':enabled'))).toHaveCount(0)
  await expect(link).toHaveText('Planned')
  await expect(link).toHaveAttribute('href', `/ui/help/vision#${section}`)
}

test.describe('with a Use Case that declares Consumers', () => {
  test.use({ seed: 'support_use_case_consumers' })

  test('the pipeline strip shows the live parts, the Consumers count and a planned Consumer Gate', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/versions')

    const strip = page.getByRole('list', { name: 'Pipeline' })
    await expect(strip.getByRole('listitem')).toHaveText([
      'Upstream pipeline',
      'Gate',
      'Knowledge Graph',
      /^Consumer Gate\s*Planned$/,
      'Consumers 2',
    ])
    await expectPlaceholder(strip, 'Consumer Gate', 'the-two-gate-pipeline')
    await expect(strip.getByRole('link', { name: 'Consumers 2' })).toHaveAttribute(
      'href',
      '/ui/kg/support/use-case',
    )
  })

  test('the planned Consumer Gate is muted next to the live parts, in light and dark themes', async ({
    page,
  }) => {
    for (const colorScheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme })
      await page.goto('/ui/kg/support/versions')
      const strip = page.getByRole('list', { name: 'Pipeline' })
      const color = (el: Element) => getComputedStyle(el).color
      const live = await strip.getByText('Knowledge Graph', { exact: true }).evaluate(color)
      const muted = await planned(strip, 'Consumer Gate').standIn.evaluate(color)
      expect(muted, colorScheme).not.toBe(live)
    }
  })

  test('the pipeline strip fits a phone screen without scrolling sideways', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto('/ui/kg/support/versions')

    const strip = page.getByRole('list', { name: 'Pipeline' })
    await expect(strip.getByRole('listitem')).toHaveCount(5)
    const overflow = (el: Element) => el.scrollWidth - el.clientWidth
    expect(await strip.evaluate(overflow)).toBeLessThanOrEqual(0)
    expect(await page.locator('html').evaluate(overflow)).toBeLessThanOrEqual(0)
  })

  test('each Consumer card shows its Connector and Consumer Gate as planned', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const cards = page.getByRole('region', { name: 'Consumers' }).getByRole('article')
    await expect(cards).toHaveCount(2)
    for (const card of await cards.all()) {
      await expect(planned(card, 'Connector').standIn).toHaveText('Connector: not connected')
      await expectPlaceholder(card, 'Connector', 'connector')
      await expect(planned(card, 'Consumer Gate').standIn).toHaveText('Consumer Gate: none')
      await expectPlaceholder(card, 'Consumer Gate', 'consumer-gate')
    }
  })

  test('the Use Case page offers drafting Tasks and questions with AI, disabled', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const consumers = page.getByRole('region', { name: 'Consumers' })
    await expect(
      consumers.getByRole('button', { name: 'Draft Tasks & questions with AI' }),
    ).toBeDisabled()
    await expectPlaceholder(consumers, 'Draft Tasks & questions with AI', 'ai-and-mcp-authoring')
  })

  test('the Gate result shows a Gate on Consumer impact as planned', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/2')

    const gates = page.getByRole('region', { name: 'Latest Gate result' })
    await expect(planned(gates, 'Gate on Consumer impact').standIn).toHaveText(
      'Gate on Consumer impact',
    )
    await expectPlaceholder(gates, 'Gate on Consumer impact', 'consumer-impact-and-gates-over-it')
  })

  test('a placeholder explains itself in a tooltip and links to its section of the vision', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.goto('/ui/kg/support/use-case')
    const card = page.getByRole('region', { name: 'Consumers' }).getByRole('article').first()
    const { link } = planned(card, 'Connector')

    await link.hover()
    await expect(page.getByRole('tooltip')).toContainText('Connector')

    await link.click()
    await expect(page).toHaveURL('/ui/help/vision#connector')
    await expect(page.getByRole('heading', { name: 'Connector', exact: true })).toBeInViewport()
  })
})

test('the vision page is in Help: its sections exist, its diagram draws, and repository links open on GitHub', async ({
  page,
}) => {
  await page.goto('/ui/help/vision')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/^Vision/)
  const contents = page.getByRole('navigation', { name: 'Guide' })
  await expect(contents.getByRole('link', { name: /^Vision/ })).toHaveAttribute('aria-current', 'page')
  // Every section a placeholder links to.
  for (const id of [
    'the-two-gate-pipeline',
    'consumer-gate',
    'connector',
    'consumer-impact-and-gates-over-it',
    'ai-and-mcp-authoring',
  ]) {
    await expect(page.locator(`[id="${id}"]`)).toHaveCount(1)
  }
  const body = page.getByRole('article')
  await expect(body.getByRole('figure').locator('svg')).toBeVisible()
  const glossary = body.getByRole('link', { name: 'GLOSSARY.md' })
  await expect(glossary).toHaveAttribute('href', 'https://github.com/JoaZaech/stetiq/blob/main/GLOSSARY.md')
  await expect(glossary).toHaveAttribute('target', '_blank')
})
