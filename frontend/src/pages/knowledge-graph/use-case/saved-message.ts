import type { SavedUseCase } from '@/api/use-cases'

/** What the Use Case page says after a save: a new version, or why there is none. */
export function savedMessage({ version, created, latest }: SavedUseCase): string {
  if (created) return `Saved as Use Case Version ${version.number}.`
  if (version.number === latest) {
    return `Nothing changed: Use Case Version ${version.number} already has this content, so no new version was created.`
  }
  return (
    `No new version was created: this content is the same as the earlier Use Case Version ${version.number}, ` +
    `and the same content is never registered twice. Use Case Version ${latest} is still the latest.`
  )
}
