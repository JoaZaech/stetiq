import type { Alias } from '@/api/aliases'

/** Alias names per Ontology Version number, sorted by name. */
export function aliasesByVersion(aliases: readonly Alias[]): Map<number, string[]> {
  const byVersion = new Map<number, string[]>()
  for (const alias of [...aliases].sort((a, b) => a.name.localeCompare(b.name))) {
    byVersion.set(alias.version, [...(byVersion.get(alias.version) ?? []), alias.name])
  }
  return byVersion
}
