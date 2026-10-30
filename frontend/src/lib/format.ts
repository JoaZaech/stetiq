const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** A server timestamp (ISO 8601) in the user's locale and time zone, e.g. "Oct 30, 2026, 14:05". */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}

const metric = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 4, useGrouping: false })

/** An Evaluator metric or run metric value: integers as is, others to 4 significant digits. */
export function formatMetric(value: number): string {
  return Number.isInteger(value) ? String(value) : metric.format(value)
}
