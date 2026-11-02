import type { Page } from '@playwright/test'
import { expect, test } from './fixtures'

/** The pipeline chain's step whose link is named `name`. */
function step(page: Page, name: string) {
  return page
    .getByRole('list', { name: 'Pipeline' })
    .getByRole('listitem')
    .filter({ has: page.getByRole('link', { name, exact: true }) })
}

const STEPS = ['Upstream pipeline', 'Gate', 'Knowledge Graph', 'Consumer Gate', 'Consumers']

/** The status icon of each tone (`components/status-tones.ts`), by its Lucide class. */
const ICONS = {
  success: 'svg.lucide-circle-check',
  failure: 'svg.lucide-circle-x',
  warning: 'svg.lucide-circle-alert',
  neutral: 'svg.lucide-circle-dashed',
}

async function expectIcon(page: Page, name: string, tone: keyof typeof ICONS) {
  await expect(step(page, name).locator(ICONS[tone])).toBeVisible()
}

test.describe('a Knowledge Graph with a finished run, an Observation and no Consumers', () => {
  test.use({ seed: 'support_lineage' })

  test('opens on the Overview, first in the sidebar, with a breadcrumb', async ({ page }) => {
    await page.goto('/ui/kg/support')

    await expect(page).toHaveURL('/ui/kg/support/overview')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('support')
    await expect(page.getByRole('navigation', { name: 'breadcrumb' })).toHaveText(
      /Knowledge Graphs.*support.*Overview/,
    )
    const sidebar = page.getByRole('navigation', { name: 'Main' })
    await expect(sidebar.getByRole('listitem').nth(2)).toHaveText('Overview')
    await expect(sidebar.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page')
  })

  test('shows each step with its status and one fact, linking to its page', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    const chain = page.getByRole('list', { name: 'Pipeline' })
    await expect(chain.getByRole('listitem')).toHaveCount(5)
    await expect(step(page, 'Upstream pipeline')).toHaveText(/^Upstream pipelineFinished(just now|\d+ \w+ ago)$/)
    await expectIcon(page, 'Upstream pipeline', 'success')
    await expect(step(page, 'Gate')).toHaveText('GateNot gatedv3')
    await expect(step(page, 'Knowledge Graph')).toHaveText(
      /^Knowledge GraphNo Driftproduction → v1 · observed (just now|\d+ \w+ ago)$/,
    )
    await expectIcon(page, 'Knowledge Graph', 'success')
    await expect(step(page, 'Consumer Gate')).toHaveText('Consumer GateNone declared')
    await expect(step(page, 'Consumers')).toHaveText('ConsumersNo Consumers')

    const links = Object.fromEntries(
      await Promise.all(
        STEPS.map(async (name) => [name, await chain.getByRole('link', { name, exact: true }).getAttribute('href')]),
      ),
    )
    expect(links).toEqual({
      'Upstream pipeline': '/ui/kg/support/runs',
      Gate: '/ui/kg/support/versions/3',
      'Knowledge Graph': '/ui/kg/support/observations',
      'Consumer Gate': '/ui/kg/support/use-case',
      Consumers: '/ui/kg/support/use-case',
    })
    await chain.getByRole('link', { name: 'Gate', exact: true }).click()
    await expect(page).toHaveURL('/ui/kg/support/versions/3')
  })

  test('shows five KPI tiles, each linking to where its value comes from', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    const tiles = page.getByRole('list', { name: 'Key figures' })
    await expect(tiles.getByRole('listitem')).toHaveCount(5)
    await expect(tiles.getByRole('link', { name: /^CQ coverage: / })).toHaveAttribute('href', '/ui/kg/support/use-case')
    await expect(tiles.getByRole('link', { name: /^Conformance: / })).toBeVisible()
    // v3 was never gated, and the latest Observation found no Drift.
    await expect(tiles.getByRole('link', { name: 'Gates: —' })).toHaveAttribute('href', '/ui/kg/support/versions/3')
    await expect(tiles.getByRole('link', { name: 'Drift: 0' })).toHaveAttribute('href', '/ui/kg/support/observations')
    await expect(tiles.getByRole('link', { name: 'Consumers: —' })).toBeVisible()
  })

  test('shows the recent runs, Observations, the current version and Promotions as cards', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    const runs = page.getByRole('region', { name: 'Recent runs' })
    await expect(runs.getByRole('list', { name: 'Recent runs' }).getByRole('listitem')).toHaveCount(1)
    await expect(runs.getByRole('link', { name: 'All runs' })).toHaveAttribute('href', '/ui/kg/support/runs')

    const observations = page.getByRole('region', { name: 'Latest Observations' })
    await expect(observations.getByRole('listitem').first()).toContainText('No Drift')

    // The Contract Alias points to v1; v3 is the newest.
    const version = page.getByRole('region', { name: 'Current Ontology Version' })
    await expect(version.getByRole('link', { name: 'v1', exact: true })).toBeVisible()
    await expect(version).toContainText('production')
    await expect(version.getByRole('link', { name: 'Newest v3' })).toHaveAttribute('href', '/ui/kg/support/versions/3')

    await expect(page.getByRole('region', { name: 'Recent Promotions' }).getByRole('link', { name: 'All Promotions' })).toBeVisible()
  })

  test('shows the first sentence of the description, the Evolution Mode and Edit description above the chain', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    const about = page.getByRole('region', { name: 'About' })
    await expect(about.getByText('No description')).toBeVisible()
    await expect(about.getByRole('term')).toHaveText('Evolution Mode')
    await expect(about.getByRole('definition')).toHaveText('evolving')
    await expect(about.getByRole('button', { name: 'Edit description' })).toBeEnabled()
    // No one-line header on the Overview: the Contract Alias is on the chain.
    await expect(page.getByRole('region', { name: 'Knowledge Graph' })).toHaveCount(0)
  })
})

test.describe('a Knowledge Graph with nothing yet', () => {
  test.use({ seed: 'many_knowledge_graphs' })

  test('shows every step that has no data as neutral', async ({ page }) => {
    await page.goto('/ui/kg/alpha')

    await expect(step(page, 'Upstream pipeline')).toHaveText('Upstream pipelineNo runs')
    await expect(step(page, 'Gate')).toHaveText('GateNot gatedv1')
    await expect(step(page, 'Knowledge Graph')).toHaveText('Knowledge GraphNot observedproduction → v1')
    await expect(step(page, 'Consumer Gate')).toHaveText('Consumer GateNone declared')
    await expect(step(page, 'Consumers')).toHaveText('ConsumersNo Consumers')
    for (const name of STEPS) await expectIcon(page, name, 'neutral')
  })
})

test.describe('a failed run', () => {
  test.use({ seed: 'knowledge_graphs' })

  test('fails the upstream pipeline', async ({ page }) => {
    await page.goto('/ui/kg/billing/overview')

    await expect(step(page, 'Upstream pipeline')).toHaveText(/^Upstream pipelineFailed(just now|\d+ \w+ ago)$/)
    await expectIcon(page, 'Upstream pipeline', 'failure')
  })
})

test.describe('a gated newest version', () => {
  test.use({ seed: 'support_metrics' })

  test("shows the newest version's Gate result", async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    await expect(step(page, 'Gate')).toHaveText('GateFailedv3 · 1 of 3 Gates failed')
    await expectIcon(page, 'Gate', 'failure')
  })
})

test.describe('Drift', () => {
  test.use({ seed: 'observed_support' })

  test('warns on the Knowledge Graph step when the latest Observation found Drift', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    await expect(step(page, 'Knowledge Graph')).toHaveText(
      /^Knowledge GraphDriftproduction → v1 · observed (just now|\d+ \w+ ago)$/,
    )
    await expectIcon(page, 'Knowledge Graph', 'warning')
  })
})

test.describe('Consumer Gates', () => {
  test.use({ seed: 'plant_consumer_gates' })

  test('fail when any Consumer Gate failed, counting every Consumer that declares one', async ({ page }) => {
    await page.goto('/ui/kg/plant/overview')

    await expect(step(page, 'Consumer Gate')).toHaveText('Consumer GateFailed1 of 3 passed')
    await expectIcon(page, 'Consumer Gate', 'failure')
  })
})

test.describe('Consumers', () => {
  test.use({ seed: 'support_use_case_consumers' })

  test('are ready when the latest Ontology Version is ready for every Task of each', async ({ page }) => {
    await page.goto('/ui/kg/support/overview')

    await expect(step(page, 'Consumers')).toHaveText('ConsumersReady2 of 2 ready')
    await expectIcon(page, 'Consumers', 'success')
    await expect(step(page, 'Consumer Gate')).toHaveText('Consumer GateNone declared')
  })
})

test.describe('on a phone', () => {
  test.use({ seed: 'support_use_case_consumers' })

  test('the chain fits the screen without scrolling sideways', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto('/ui/kg/support/overview')

    const chain = page.getByRole('list', { name: 'Pipeline' })
    await expect(chain.getByRole('listitem')).toHaveCount(5)
    const overflow = (el: Element) => el.scrollWidth - el.clientWidth
    expect(await chain.evaluate(overflow)).toBeLessThanOrEqual(0)
    expect(await page.locator('html').evaluate(overflow)).toBeLessThanOrEqual(0)
  })
})
