import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

test.use({ seed: 'ontology_map' })

const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })

/** A class's drawn shape: the node's own box is transparent, its shape is its first child. */
const shape = (map: Locator, label: string) =>
  map.getByRole('group', { name: label, exact: true }).locator(':scope > *').first()

const change = (map: Locator, label: string) =>
  shape(map, label).evaluate((el: HTMLElement) => [el.dataset.change, el.dataset.severity ?? null])

test('the Compare page superimposes two non-adjacent versions on a Map', async ({ page }) => {
  await page.goto('/ui/kg/support/versions')
  await page.getByRole('checkbox', { name: 'Select v3' }).check()
  await page.getByRole('checkbox', { name: 'Select v1' }).check()
  await page.getByRole('button', { name: 'Compare' }).click()

  await expect(page).toHaveURL('/ui/kg/support/versions/compare?id=1&id=3')
  await expect(page.getByRole('radio', { name: 'Table' })).toBeChecked()
  await expect(page.getByRole('region', { name: 'Ontology Diff' })).toBeVisible()

  await page.getByRole('radio', { name: 'Map' }).click()

  await expect(page).toHaveURL('/ui/kg/support/versions/compare?id=1&id=3&view=map')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare v1 → v3')
  const expectMap = async () => {
    const map = ontologyMap(page)
    // Queue arrived in v2 and Team in v3: both are additions since v1.
    await expect.poll(() => change(map, 'Queue')).toEqual(['added', 'additive'])
    await expect.poll(() => change(map, 'Team')).toEqual(['added', 'additive'])
    await expect.poll(() => change(map, 'Product')).toEqual(['removed', 'breaking'])
    await expect.poll(() => change(map, 'Ticket')).toEqual(['modified', 'breaking'])
    await expect.poll(() => change(map, 'Customer')).toEqual(['unchanged', null])
  }
  await expectMap()

  // The URL alone reopens the same comparison on the Map.
  await page.reload()
  await expectMap()

  // Back to the Table keeps the chosen versions.
  await page.getByRole('radio', { name: 'Table' }).click()
  await expect(page).toHaveURL('/ui/kg/support/versions/compare?id=1&id=3')
  await expect(page.getByRole('region', { name: 'Ontology Diff' })).toBeVisible()
})

test('picking other versions updates the Map', async ({ page }) => {
  await page.goto('/ui/kg/support/versions/compare?id=1&id=3&view=map')
  const map = ontologyMap(page)
  await expect.poll(() => change(map, 'Queue')).toEqual(['added', 'additive'])

  await page.goto('/ui/kg/support/versions/compare?id=2&id=3&view=map')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare v2 → v3')
  // Against v2, Queue was already there: v3 only deprecates it. Product was gone already.
  await expect.poll(() => change(map, 'Queue')).toEqual(['modified', 'deprecating'])
  await expect.poll(() => change(map, 'Team')).toEqual(['added', 'additive'])
  await expect.poll(() => change(map, 'Ticket')).toEqual(['unchanged', null])
  await expect(map.getByRole('group', { name: 'Product', exact: true })).toHaveCount(0)
})
