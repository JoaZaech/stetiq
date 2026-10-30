import { useOutletContext } from 'react-router'
import type { ConstructionRun } from '@/api/runs'

/** The Construction Run a run tab (a child route of the run page) shows. */
export function useConstructionRunTab(): ConstructionRun {
  return useOutletContext<ConstructionRun>()
}
