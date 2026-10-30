import { Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'
import { ApiError } from '@/api/client'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ThemeProvider } from '@/theme/ThemeProvider'
import { router } from './router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 4xx (not found, no access) will not change on retry; a network blip may.
      retry: (failures, error) =>
        !(error instanceof ApiError && error.status < 500) && failures < 2,
      refetchOnWindowFocus: false,
    },
  },
})

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          {/* Pages load lazily (router.tsx); the sign-in page has no layout to wait in. */}
          <Suspense fallback={null}>
            <RouterProvider router={router} />
          </Suspense>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
