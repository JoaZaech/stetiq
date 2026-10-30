const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** A server timestamp (ISO 8601) in the user's locale and time zone. */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}
