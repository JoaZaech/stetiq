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

const points = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })
const signedPoints = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1, signDisplay: 'exceptZero' })

/**
 * A difference of two ratios in percentage points, to one decimal at most: 0.025 → "2.5 pts";
 * only a difference that shows as exactly 1 is singular, "1 pt". `signed` adds the sign, with
 * a true minus: "+2.5 pts", "−10 pts".
 */
export function formatPoints(delta: number, { signed = false } = {}): string {
  const value = delta * 100
  const text = (signed ? signedPoints : points).format(value).replace('-', '−')
  return `${text} ${points.format(Math.abs(value)) === points.format(1) ? 'pt' : 'pts'}`
}

/** A count out of its total: "5 / 6". */
export function formatFraction(count: number, total: number): string {
  return `${formatMetric(count)} / ${formatMetric(total)}`
}

/** `n` and `noun`, the noun plural unless `n` is 1: "1 attribute", "3 attributes", "2 classes". */
export function formatCount(n: number, noun: string, plural = `${noun}s`): string {
  return `${n} ${n === 1 ? noun : plural}`
}
