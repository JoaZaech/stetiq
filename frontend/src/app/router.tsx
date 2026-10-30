import { createBrowserRouter, type RouteObject } from 'react-router'
import { KnowledgeGraphsPage } from '@/pages/knowledge-graphs/KnowledgeGraphsPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { SettingsPage } from '@/pages/settings/SettingsPage'
import { SignInPage } from '@/pages/sign-in/SignInPage'
import { AppLayout } from './AppLayout'
import type { RouteHandle } from './breadcrumbs'

const crumb = (label: RouteHandle['crumb']): RouteHandle => ({ crumb: label })

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
        children: [
          { index: true, element: <KnowledgeGraphsPage /> },
          // Knowledge Graph pages go here, e.g.
          // { path: 'kg/:name', handle: crumb(({ name }) => name ?? ''), children: [...] },
        ],
      },
      { path: 'settings', element: <SettingsPage />, handle: crumb(() => 'Settings') },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes, { basename: '/ui' })
