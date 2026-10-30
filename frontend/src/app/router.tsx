import type { ReactNode } from 'react'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { KnowledgeGraphLayout } from '@/pages/knowledge-graph/KnowledgeGraphLayout'
import { KnowledgeGraphSectionPage } from '@/pages/knowledge-graph/KnowledgeGraphSectionPage'
import { KnowledgeGraphsPage } from '@/pages/knowledge-graphs/KnowledgeGraphsPage'
import { ObservationsPage } from '@/pages/knowledge-graph/observations/ObservationsPage'
import { OntologyTab } from '@/pages/knowledge-graph/versions/OntologyTab'
import { OntologyVersionPage } from '@/pages/knowledge-graph/versions/OntologyVersionPage'
import { OntologyVersionsPage } from '@/pages/knowledge-graph/versions/OntologyVersionsPage'
import { OverviewTab } from '@/pages/knowledge-graph/versions/OverviewTab'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SettingsPage } from '@/pages/settings/SettingsPage'
import { SignInPage } from '@/pages/sign-in/SignInPage'
import { AppLayout } from './AppLayout'
import type { RouteHandle } from './breadcrumbs'
import {
  DEFAULT_SECTION,
  KNOWLEDGE_GRAPH_SECTIONS,
  type KnowledgeGraphSectionPath,
} from './knowledge-graph-sections'

const crumb = (label: RouteHandle['crumb']): RouteHandle => ({ crumb: label })

/**
 * What each Knowledge Graph section shows at `/kg/:name/<section>`:
 * - `page`: its landing page, which starts with `<KnowledgeGraphSectionPage section=…>`
 *   (Knowledge Graph header + section title). Omitted: a placeholder.
 * - `children`: detail pages under it, e.g. `{ path: ':number', … }`; they get the
 *   section's breadcrumb first and render their own `PageHeader`.
 */
const knowledgeGraphSectionRoutes: Record<
  KnowledgeGraphSectionPath,
  { page?: ReactNode; children?: RouteObject[] }
> = {
  versions: {
    page: <OntologyVersionsPage />,
    children: [
      {
        path: ':number',
        element: <OntologyVersionPage />,
        handle: crumb(({ number }) => `v${number}`),
        // The version page's tabs (see TABS in OntologyVersionPage).
        children: [
          { index: true, element: <OverviewTab /> },
          { path: 'ontology', element: <OntologyTab /> },
        ],
      },
    ],
  },
  runs: {},
  'use-case': {},
  observations: { page: <ObservationsPage /> },
  promotions: {},
}

const knowledgeGraphRoute: RouteObject = {
  path: 'kg/:name',
  element: <KnowledgeGraphLayout />,
  handle: crumb(({ name }) => name ?? ''),
  children: [
    { index: true, element: <Navigate to={DEFAULT_SECTION} replace /> },
    ...KNOWLEDGE_GRAPH_SECTIONS.map((section): RouteObject => {
      const { page, children = [] } = knowledgeGraphSectionRoutes[section.path]
      return {
        path: section.path,
        handle: crumb(() => section.label),
        children: [
          { index: true, element: page ?? <KnowledgeGraphSectionPage section={section} /> },
          ...children,
        ],
      }
    }),
    { path: '*', element: <NotFoundPage /> },
  ],
}

/**
 * Every page of the app. Paths are relative to `/ui` (the router's basename).
 * A route with `handle: crumb(...)` adds a breadcrumb that links to its path.
 */
export const routes: RouteObject[] = [
  // Server mode only; outside the layout, so it shows no sidebar and asks for no data.
  { path: 'sign-in', element: <SignInPage /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        // Pathless: puts "Knowledge Graphs" first in the breadcrumbs of every page below.
        handle: crumb(() => 'Knowledge Graphs'),
        children: [{ index: true, element: <KnowledgeGraphsPage /> }, knowledgeGraphRoute],
      },
      { path: 'settings', element: <SettingsPage />, handle: crumb(() => 'Settings') },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes, { basename: '/ui' })
