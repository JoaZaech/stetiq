const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** A server timestamp (ISO 8601) in the user's locale and time zone, e.g. "Oct 30, 2026, 14:05". */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'always' })
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/** How long ago a server timestamp was, in its largest whole unit: "5 minutes ago", "just now". */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const seconds = (now.getTime() - new Date(iso).getTime()) / 1000
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(-Math.trunc(seconds / size), unit)
  }
  return 'just now'
}

const metric = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 4, useGrouping: false })

/** An Evaluator metric or run metric value: integers as is, others to 4 significant digits. */
export function formatMetric(value: number): string {
  return Number.isInteger(value) ? String(value) : metric.format(value)
}

const percent = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 })

/** A ratio between 0 and 1 as a percentage, to one decimal at most: 0.7097 → "71%", 0.995 → "99.5%". */
export function formatPercent(ratio: number): string {
  return percent.format(ratio)
}

/** A count out of its total: "5 / 6". */
export function formatFraction(count: number, total: number): string {
  return `${formatMetric(count)} / ${formatMetric(total)}`
}

/** `n` and `noun`, the noun plural unless `n` is 1: "1 attribute", "3 attributes", "2 classes". */
export function formatCount(n: number, noun: string, plural = `${noun}s`): string {
  return `${n} ${n === 1 ? noun : plural}`
}
