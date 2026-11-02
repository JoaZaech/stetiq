import { useOutletContext } from 'react-router'
import type { ConstructionRun } from '@/api/runs'

/** The Construction Run a run tab (a child route of the run page) shows. */
export function useConstructionRunTab(): ConstructionRun {
  return useOutletContext<ConstructionRun>()
}

/** The Evaluation tab's search param that opens its findings filtered to one finding. */
export const FINDING_PARAM = 'finding'
