import { type Locator, type Page } from '@playwright/test'
import { expect, test } from './fixtures'

// city-transit v2 → v3: two breaking attribute renames (each a removal and an addition) and
// HAS_TRIP gaining a description, which is documentation-only.
test.use({ seed: 'ontology_map_transit' })

const changes = (page: Page) => page.getByRole('table', { name: 'Changes' })
/** The grid's rows by their first cell, the Concept. */
const concepts = (page: Page) => changes(page).getByRole('row').locator('td:first-child')
const row = (table: Locator, concept: string) =>
  table.getByRole('row').filter({ has: table.page().getByRole('cell', { name: concept, exact: true }) })
const ontologyMap = (page: Page) => page.getByRole('application', { name: 'Ontology Map' })
const shape = (map: Locator, label: string) =>
  map.getByRole('group', { name: label, exact: true }).locator(':scope > *').first()

test('the Changes tab lists the changes as a grid, documentation-only ones hidden until asked for', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes?view=table')

  const headers = changes(page).getByRole('columnheader')
  await expect(headers).toHaveText(['Concept', 'Concept kind', 'Change', 'Severity', 'Detail', ''])
  await expect(concepts(page)).toHaveText([
    'Stop.wheelchairBoarding',
    'Trip.bikesAllowed',
    'Stop.wheelchair_boarding',
    'Trip.bikes_allowed',
  ])
  await expect(row(changes(page), 'Stop.wheelchairBoarding')).toHaveText(/attribute.*removed.*breaking/)
  await expect(page.getByText('4 changes', { exact: true })).toBeVisible()

  // HAS_TRIP only gained a description: hidden, but counted, and one click away.
  await expect(page.getByText('1 documentation-only change hidden')).toBeVisible()
  await page.getByRole('button', { name: 'Show documentation-only changes' }).click()
  await expect(page).toHaveURL(/changes\.docs=1/)
  await expect(row(changes(page), 'HAS_TRIP')).toHaveText(/relation.*changed.*documentation-only.*description changed/)
  await expect(page.getByText('5 changes', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Hide documentation-only changes' }).click()
  await expect(row(changes(page), 'HAS_TRIP')).toHaveCount(0)
})

test('the Compare page’s grid sorts, filters and searches in the URL beside the chosen versions', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/compare?id=2&id=3&view=table')

  await changes(page).getByRole('button', { name: 'Concept', exact: true }).click()
  await expect(concepts(page)).toHaveText([
    'Stop.wheelchair_boarding',
    'Stop.wheelchairBoarding',
    'Trip.bikes_allowed',
    'Trip.bikesAllowed',
  ])

  await changes(page).getByRole('button', { name: 'Filter Change' }).click()
  await page.getByRole('checkbox', { name: 'removed' }).click()
  await page.keyboard.press('Escape')
  await expect(concepts(page)).toHaveText(['Stop.wheelchairBoarding', 'Trip.bikesAllowed'])

  await page.getByRole('searchbox', { name: 'Search changes' }).fill('trip')
  await expect(concepts(page)).toHaveText(['Trip.bikesAllowed'])
  await expect(page.getByText('1 of 4 changes')).toBeVisible()

  await expect(page).toHaveURL(/\?id=2&id=3&/)
  await expect(page).toHaveURL(/changes\.sort=concept/)
  await expect(page).toHaveURL(/changes\.f\.change=removed/)
  await expect(page).toHaveURL(/changes\.q=trip/)

  // The URL alone reproduces it.
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Compare v2 → v3')
  await expect(concepts(page)).toHaveText(['Trip.bikesAllowed'])
})

test('“Show on Map” selects a change’s Concept on the comparison Map', async ({ page }) => {
  await page.goto('/ui/kg/city-transit/versions/3/changes?view=table')

  // An attribute shows as its class.
  await row(changes(page), 'Stop.wheelchairBoarding').getByRole('button', { name: 'Show Stop on Map' }).click()

  await expect(page).toHaveURL(/\/changes\?select=class%3AStop$/)
  await expect(shape(ontologyMap(page), 'Stop')).toHaveAttribute('data-selected')

  // So does the Compare page's.
  await page.goto('/ui/kg/city-transit/versions/compare?id=2&id=3&view=table')
  await row(changes(page), 'Trip.bikesAllowed').getByRole('button', { name: 'Show Trip on Map' }).click()
  await expect(page).toHaveURL(/\?id=2&id=3&select=class%3ATrip$/)
  await expect(shape(ontologyMap(page), 'Trip')).toHaveAttribute('data-selected')
})
