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

  test('the Overview shows every step of the pipeline live, the Consumer Gate included', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    const strip = page.getByRole('list', { name: 'Pipeline' })
    await expect(strip.getByRole('link')).toHaveText([
      'Upstream pipeline',
      'Gate',
      'Knowledge Graph',
      'Consumer Gate',
      'Consumers',
    ])
    await expect(strip.getByRole('link', { name: /^Planned/ })).toHaveCount(0)
    await expect(strip.getByRole('group', { name: 'Consumer Gate' })).toHaveCount(0)
  })

  test('the Consumer Gate step is drawn like the other live steps, in light and dark themes', async ({
    page,
  }) => {
    for (const colorScheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme })
      await page.goto('/ui/kg/support/overview')
      const strip = page.getByRole('list', { name: 'Pipeline' })
      const style = (el: Element) => `${getComputedStyle(el).color} ${getComputedStyle(el.parentElement!).borderStyle}`
      const gate = await strip.getByRole('link', { name: 'Gate', exact: true }).evaluate(style)
      const consumerGate = await strip.getByRole('link', { name: 'Consumer Gate' }).evaluate(style)
      expect(consumerGate, colorScheme).toBe(gate)
      expect(consumerGate, colorScheme).not.toContain('dashed')
    }
  })

  test('the Consumer sheet shows evaluating its Consumer Gate on each Observation as planned', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    await page.getByRole('button', { name: 'Triage bot' }).click()
    const gate = page.getByRole('dialog', { name: 'Triage bot' }).getByRole('region', { name: 'Consumer Gate' })
    await expect(gate).toContainText('No Consumer Gate declared')
    await expect(planned(gate, 'Evaluated on each Observation').standIn).toHaveText('Evaluated on each Observation')
    await expectPlaceholder(gate, 'Evaluated on each Observation', 'consumer-gate')
  })

  test('every Consumer tile has Connect, badged Planned, which opens the Connector picker and not the sheet', async ({
    page,
  }) => {
    await page.goto('/ui/kg/support/use-case')

    const tiles = page.getByRole('region', { name: 'Consumers' }).getByRole('article')
    await expect(tiles).toHaveCount(2)
    for (const tile of await tiles.all()) {
      await expect(tile.getByRole('button', { name: 'Connect', exact: true })).toBeEnabled()
      const badge = tile.getByRole('link', { name: 'Planned: Connect', exact: true })
      await expect(badge).toHaveText('Planned')
      await expect(badge).toHaveAttribute('href', '/ui/help/vision#connector')
      await expect(tile).not.toContainText('Integration')
    }

    const url = page.url()
    await tiles
      .filter({ has: page.getByRole('button', { name: 'Triage bot' }) })
      .getByRole('button', { name: 'Connect', exact: true })
      .click()
    const picker = page.getByRole('dialog', { name: 'Connect Triage bot' })
    await expect(picker).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(1)
    expect(page.url()).toBe(url)
    await expect(picker).not.toContainText('Integration')

    await expect(picker.getByRole('region').getByRole('heading', { level: 3 })).toHaveText([
      'Enforce in CI',
      'Get notified',
      "In the Consumer's code",
    ])
    const tools = {
      'Enforce in CI': ['GitHub Actions', 'GitLab CI'],
      'Get notified': ['Webhook', 'Slack', 'GitHub Issues'],
      "In the Consumer's code": ['LangChain', 'LlamaIndex'],
    }
    for (const [group, names] of Object.entries(tools)) {
      const tiles = picker.getByRole('region', { name: group }).getByRole('article')
      await expect(tiles.getByRole('heading')).toHaveText(names)
      for (const name of names) {
        const tool = tiles.filter({ has: page.getByRole('heading', { name, exact: true }) })
        await expect(tool.getByRole('button', { name: 'Connect' })).toBeDisabled()
        await expectPlaceholder(tool, name, 'connector')
      }
    }
    await expect(picker.getByRole('button', { name: 'Connect' })).toHaveCount(7)
    await expect(picker.locator('button:enabled', { hasText: 'Connect' })).toHaveCount(0)
  })

  test('the Use Case page offers drafting Tasks and questions with AI, disabled', async ({ page }) => {
    await page.goto('/ui/kg/support/use-case')

    const consumers = page.getByRole('region', { name: 'Consumers' })
    await expect(
      consumers.getByRole('button', { name: 'Draft Tasks & questions with AI' }),
    ).toBeDisabled()
    await expect(consumers.locator('button:disabled')).toHaveCount(1)
    await expectPlaceholder(consumers, 'Draft Tasks & questions with AI', 'ai-and-mcp-authoring')
  })

  test('the Gate result shows a Gate on Consumer impact as planned', async ({ page }) => {
    await page.goto('/ui/kg/support/versions/2')

    const gates = page.getByRole('region', { name: 'Gate result' })
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
    const { link } = planned(page.getByRole('region', { name: 'Consumers' }), 'Draft Tasks & questions with AI')

    await link.hover()
    await expect(page.getByRole('tooltip')).toContainText('Tasks and Competency Questions')

    await link.click()
    await expect(page).toHaveURL('/ui/help/vision#ai-and-mcp-authoring')
    await expect(page.getByRole('heading', { name: 'AI and MCP authoring', exact: true })).toBeInViewport()
  })
})

test.describe('with Drift that finds an undeclared Concept', () => {
  test.use({ seed: 'observed_support' })

  test('the Drift event shows Pending Migration and Adoption as planned', async ({ page }) => {
    await page.goto('/ui/kg/support/observations')

    const row = page.getByRole('list', { name: 'Observations' }).getByRole('listitem').first()
    await row.getByRole('button', { name: 'Drift details' }).click()
    const drift = row.getByRole('region', { name: 'Drift' })
    await expect(planned(drift, 'Pending Migration').standIn).toHaveText('Pending Migration')
    await expectPlaceholder(drift, 'Pending Migration', 'pending-migration-and-adoption')
    await expect(drift.getByRole('button', { name: 'Adopt into a Candidate' })).toBeDisabled()
    await expectPlaceholder(drift, 'Adoption', 'pending-migration-and-adoption')
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
    'pending-migration-and-adoption',
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
