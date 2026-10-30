import type { Alias, Promotion } from '@/api/aliases'

/** Alias names per Ontology Version number, sorted by name. */
export function aliasesByVersion(aliases: readonly Alias[]): Map<number, string[]> {
  const byVersion = new Map<number, string[]>()
  for (const alias of [...aliases].sort((a, b) => a.name.localeCompare(b.name))) {
    byVersion.set(alias.version, [...(byVersion.get(alias.version) ?? []), alias.name])
  }
  return byVersion
}

/**
 * A Candidate is a version no Alias has pointed to yet: no Promotion ever moved an
 * Alias to it (as `Client.latest_candidate` decides).
 */
export function candidateVersions(
  versions: readonly { number: number }[],
  promotions: readonly Promotion[],
): Set<number> {
  const promoted = new Set(promotions.map((p) => p.to_version))
  return new Set(versions.map((v) => v.number).filter((n) => !promoted.has(n)))
}
