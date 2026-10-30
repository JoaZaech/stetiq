import { useOutletContext } from 'react-router'
import type { OntologyVersion } from '@/api/ontology-versions'

/** The Ontology Version a version tab (a child route of the version page) shows. */
export function useOntologyVersionTab(): OntologyVersion {
  return useOutletContext<OntologyVersion>()
}
