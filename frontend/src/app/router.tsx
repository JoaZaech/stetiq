import { lazy, type ComponentType, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { KnowledgeGraphLayout } from '@/pages/knowledge-graph/KnowledgeGraphLayout'
import { KnowledgeGraphSectionPage } from '@/pages/knowledge-graph/KnowledgeGraphSectionPage'
import { shortRunId } from '@/pages/knowledge-graph/runs/runs'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { AppLayout } from './AppLayout'
import type { RouteHandle } from './breadcrumbs'
import {
  DEFAULT_SECTION,
  KNOWLEDGE_GRAPH_SECTIONS,
  type KnowledgeGraphSectionPath,
} from './knowledge-graph-sections'

const crumb = (label: RouteHandle['crumb']): RouteHandle => ({ crumb: label })

/**
 * A page loaded the first time it is shown, so the main bundle holds only the app shell.
 * Router navigations are transitions: the previous page stays up while one loads.
 */
function lazyPage<M>(load: () => Promise<M>, pick: (module: M) => ComponentType): ComponentType {
  return lazy(async () => ({ default: pick(await load()) }))
}

const ConstructionRunPage = lazyPage(() => import('@/pages/knowledge-graph/runs/ConstructionRunPage'), (m) => m.ConstructionRunPage)
const ConstructionRunsPage = lazyPage(() => import('@/pages/knowledge-graph/runs/ConstructionRunsPage'), (m) => m.ConstructionRunsPage)
const RunComparePage = lazyPage(() => import('@/pages/knowledge-graph/runs/RunComparePage'), (m) => m.RunComparePage)
const RunConformanceTab = lazyPage(() => import('@/pages/knowledge-graph/runs/RunConformanceTab'), (m) => m.RunConformanceTab)
const RunEvaluationsTab = lazyPage(() => import('@/pages/knowledge-graph/runs/RunEvaluationsTab'), (m) => m.RunEvaluationsTab)
const RunOverviewTab = lazyPage(() => import('@/pages/knowledge-graph/runs/RunOverviewTab'), (m) => m.RunOverviewTab)
const KnowledgeGraphsPage = lazyPage(() => import('@/pages/knowledge-graphs/KnowledgeGraphsPage'), (m) => m.KnowledgeGraphsPage)
const ChangesTab = lazyPage(() => import('@/pages/knowledge-graph/versions/ChangesTab'), (m) => m.ChangesTab)
const OntologyDiffPage = lazyPage(() => import('@/pages/knowledge-graph/versions/OntologyDiffPage'), (m) => m.OntologyDiffPage)
const ObservationsPage = lazyPage(() => import('@/pages/knowledge-graph/observations/ObservationsPage'), (m) => m.ObservationsPage)
const OntologyTab = lazyPage(() => import('@/pages/knowledge-graph/versions/OntologyTab'), (m) => m.OntologyTab)
const OntologyVersionPage = lazyPage(() => import('@/pages/knowledge-graph/versions/OntologyVersionPage'), (m) => m.OntologyVersionPage)
const OntologyVersionsPage = lazyPage(() => import('@/pages/knowledge-graph/versions/OntologyVersionsPage'), (m) => m.OntologyVersionsPage)
const OverviewTab = lazyPage(() => import('@/pages/knowledge-graph/versions/OverviewTab'), (m) => m.OverviewTab)
const PromotionsPage = lazyPage(() => import('@/pages/knowledge-graph/promotions/PromotionsPage'), (m) => m.PromotionsPage)
const SettingsPage = lazyPage(() => import('@/pages/settings/SettingsPage'), (m) => m.SettingsPage)
const SignInPage = lazyPage(() => import('@/pages/sign-in/SignInPage'), (m) => m.SignInPage)
const UseCaseComparePage = lazyPage(() => import('@/pages/knowledge-graph/use-case/UseCaseComparePage'), (m) => m.UseCaseComparePage)
const UseCasePage = lazyPage(() => import('@/pages/knowledge-graph/use-case/UseCasePage'), (m) => m.UseCasePage)

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
      // ?id=<base>&id=<target>: two rows selected in the version table.
      { path: 'compare', element: <OntologyDiffPage />, handle: crumb(() => 'Compare') },
      {
        path: ':number',
        element: <OntologyVersionPage />,
        handle: crumb(({ number }) => `v${number}`),
        // The version page's tabs (see TABS in OntologyVersionPage).
        children: [
          { index: true, element: <OverviewTab /> },
          { path: 'ontology', element: <OntologyTab /> },
          { path: 'changes', element: <ChangesTab /> },
        ],
      },
    ],
  },
  runs: {
    page: <ConstructionRunsPage />,
    children: [
      // ?id=&id=…: the runs selected in the run table.
      { path: 'compare', element: <RunComparePage />, handle: crumb(() => 'Compare') },
      {
        path: ':runId',
        element: <ConstructionRunPage />,
        handle: crumb(({ runId }) => shortRunId(runId ?? '')),
        // The run page's tabs (see TABS in ConstructionRunPage).
        children: [
          { index: true, element: <RunOverviewTab /> },
          { path: 'conformance', element: <RunConformanceTab /> },
          { path: 'evaluations', element: <RunEvaluationsTab /> },
        ],
      },
    ],
  },
  'use-case': {
    page: <UseCasePage />,
    children: [{ path: 'compare', element: <UseCaseComparePage />, handle: crumb(() => 'Compare') }],
  },
  observations: { page: <ObservationsPage /> },
  promotions: { page: <PromotionsPage /> },
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
