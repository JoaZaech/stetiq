/**
 * A searchable grid of line charts, one per metric (Recharts). Generic over the x-axis:
 * the caller says how to label and format x (a version number, a run's start time...).
 *
 * Recharts is large, so pages load this module lazily:
 *   const MetricChartGrid = lazy(() => import('@/components/MetricChartGrid'))
 * and wrap it in `<Suspense>`. Shape the data with `metricSeries` (`@/lib/metric-charts`).
 *
 * A series' `references` are drawn as dashed lines and listed in text ("Bounds"); a
 * point's `status` colours it pass (circle) or fail (diamond) and names it in its label.
 * Points without a status keep the neutral series colour.
 */
import { type KeyboardEvent, useId, useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { SearchInput } from '@/components/SearchInput'
import { formatMetric } from '@/lib/format'
import { type ChartPoint, filterMetricSeries, type MetricSeries } from '@/lib/metric-charts'

export interface MetricChartXAxis {
  /** What x is, e.g. "Ontology Version"; shown in the tooltip. */
  label: string
  /** Tick and tooltip text for an x value, e.g. `(x) => \`v${x}\``. */
  format: (x: number) => string
  /** Explicit tick positions (e.g. every version number); Recharts picks them when omitted. */
  ticks?: number[]
  /** `time` spaces ticks for epoch-millisecond x values. */
  scale?: 'linear' | 'time'
}

interface MetricChartGridProps<S extends MetricSeries> {
  series: readonly S[]
  xAxis: MetricChartXAxis
  /** The "Search metric charts" text (e.g. from `useChartSearch()`). */
  search: string
  onSearchChange: (search: string) => void
  /** Called when a point is clicked (or Enter/Space on a focused point); points are buttons then. */
  onPointClick?: (series: S, point: ChartPoint) => void
}

export default function MetricChartGrid<S extends MetricSeries>({
  series,
  xAxis,
  search,
  onSearchChange,
  onPointClick,
}: MetricChartGridProps<S>) {
  const id = useId()
  const shown = useMemo(() => filterMetricSeries(series, search), [series, search])
  // Every chart spans the same x range, so charts line up when read side by side.
  const domain = useMemo(() => xDomain(series), [series])
  const keys = useMemo(() => chartKeys(series), [series])
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h3 id={id} className="sr-only">
        Metric charts
      </h3>
      <SearchInput label="Search metric charts" value={search} onChange={onSearchChange} />
      {series.length === 0 ? (
        <p className="text-sm text-muted-foreground">No metrics to chart yet.</p>
      ) : shown.length === 0 ? (
        <p className="text-sm text-muted-foreground">No metric charts match “{search}”.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((s) => (
            <MetricChart
              key={keys.get(s)}
              series={s}
              xAxis={xAxis}
              domain={domain}
              onPointClick={onPointClick && ((point) => onPointClick(s, point))}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function MetricChart({
  series,
  xAxis,
  domain,
  onPointClick,
}: {
  series: MetricSeries
  xAxis: MetricChartXAxis
  domain: [number, number]
  onPointClick?: (point: ChartPoint) => void
}) {
  const axisTick = { fontSize: 11, fill: 'var(--muted-foreground)' }
  const references = series.references ?? []
  const judged = series.points.some((p) => p.status !== undefined)
  const pointLabel = (p: ChartPoint) =>
    `${xAxis.format(p.x)}: ${formatMetric(p.value)}${p.status ? `, ${p.status.label}` : ''}`
  return (
    <figure className="min-w-0 rounded-lg border p-3">
      <figcaption className="truncate text-xs font-medium" title={series.metric}>
        {series.metric}
      </figcaption>
      {(references.length > 0 || judged || series.note) && (
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {judged && (
            <span className="inline-flex items-center gap-2" aria-hidden>
              <span className="inline-flex items-center gap-1">
                <svg viewBox="0 0 10 10" className="size-2.5">
                  <circle cx="5" cy="5" r="4" className={STATUS_FILL.pass} />
                </svg>
                pass
              </span>
              <span className="inline-flex items-center gap-1">
                <svg viewBox="0 0 10 10" className="size-2.5">
                  <path d="M5 0 L10 5 L5 10 L0 5 Z" className={STATUS_FILL.fail} />
                </svg>
                fail
              </span>
            </span>
          )}
          {references.length > 0 && (
            <ul aria-label="Bounds" className="inline-flex flex-wrap gap-x-2">
              {references.map((r) => (
                <li key={`${r.name} ${r.label}`} className="inline-flex items-center gap-1">
                  <svg viewBox="0 0 12 2" className="h-0.5 w-3" aria-hidden>
                    <line x1="0" y1="1" x2="12" y2="1" stroke="currentColor" strokeWidth="2" strokeDasharray="3 2" />
                  </svg>
                  {r.name}: {r.label}
                </li>
              ))}
            </ul>
          )}
          {series.note && <p role="note">{series.note}</p>}
        </div>
      )}
      <div className="mt-2 h-40">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series.points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="x"
              type="number"
              scale={xAxis.scale === 'time' ? 'time' : 'linear'}
              domain={domain}
              ticks={xAxis.ticks}
              tickFormatter={xAxis.format}
              allowDecimals={false}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
            />
            <YAxis
              width={44}
              tickFormatter={(v: number) => formatMetric(v)}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ stroke: 'var(--muted-foreground)', strokeDasharray: '3 3' }}
              labelFormatter={(x) => `${xAxis.label} ${xAxis.format(Number(x))}`}
              formatter={(value, _name, item) => {
                const status = (item.payload as ChartPoint | undefined)?.status
                return [`${formatMetric(Number(value))}${status ? ` · ${status.label}` : ''}`, series.metric]
              }}
              contentStyle={{
                background: 'var(--popover)',
                borderColor: 'var(--border)',
                color: 'var(--popover-foreground)',
                fontSize: 12,
                borderRadius: 6,
              }}
              itemStyle={{ color: 'var(--popover-foreground)' }}
            />
            {references.map((r) => (
              <ReferenceLine
                key={`${r.name} ${r.label}`}
                y={r.value}
                ifOverflow="extendDomain"
                stroke="var(--muted-foreground)"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                label={{
                  value: r.label,
                  position: 'insideTopRight',
                  fontSize: 10,
                  fill: 'var(--muted-foreground)',
                }}
              />
            ))}
            <Line
              dataKey="value"
              type="linear"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={(props: DotProps) => (
                <PointMark key={props.index} {...props} label={pointLabel} onClick={onPointClick} />
              )}
              activeDot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

/** Pass and fail fills: the app's status colours (the `success` and `destructive` tokens, as `StatusLabel`). */
const STATUS_FILL = {
  pass: 'fill-success',
  fail: 'fill-destructive',
} as const

/** What Recharts passes a custom dot. */
interface DotProps {
  cx?: number
  cy?: number
  index?: number
  payload?: ChartPoint
}

/**
 * One point: neutral, or pass (circle) / fail (diamond) in its status colour, with a
 * 2px surface ring and a hit target larger than the mark. A button when clickable.
 */
function PointMark({
  cx,
  cy,
  payload,
  label,
  onClick,
}: DotProps & {
  label: (p: ChartPoint) => string
  onClick?: (point: ChartPoint) => void
}) {
  if (cx === undefined || cy === undefined || payload === undefined) return null
  const point = payload
  const status = point.status
  const ring = { stroke: 'var(--card)', strokeWidth: 2 }
  const activate = onClick && (() => onClick(point))
  const onKeyDown =
    activate &&
    ((e: KeyboardEvent<SVGGElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        activate()
      }
    })
  return (
    <g
      role={activate ? 'button' : 'img'}
      aria-label={label(point)}
      data-status={status === undefined ? undefined : status.passed ? 'pass' : 'fail'}
      tabIndex={activate ? 0 : undefined}
      onClick={activate}
      onKeyDown={onKeyDown}
      className={activate ? 'cursor-pointer outline-none focus-visible:[&>.mark]:stroke-ring' : undefined}
    >
      <circle cx={cx} cy={cy} r={10} fill="transparent" />
      {status === undefined ? (
        <circle className="mark" cx={cx} cy={cy} r={4} fill="var(--primary)" {...ring} />
      ) : status.passed ? (
        <circle className={`mark ${STATUS_FILL.pass}`} cx={cx} cy={cy} r={4.5} {...ring} />
      ) : (
        <path
          className={`mark ${STATUS_FILL.fail}`}
          d={`M${cx} ${cy - 6} L${cx + 6} ${cy} L${cx} ${cy + 6} L${cx - 6} ${cy} Z`}
          {...ring}
        />
      )}
    </g>
  )
}

/**
 * A React key per series: its metric, numbered when several series share a name (e.g. a
 * run metric named like an Evaluator KPI), so the key holds while the search filters.
 */
function chartKeys<S extends MetricSeries>(series: readonly S[]): Map<S, string> {
  const seen = new Map<string, number>()
  return new Map(
    series.map((s) => {
      const n = seen.get(s.metric) ?? 0
      seen.set(s.metric, n + 1)
      return [s, n === 0 ? s.metric : `${s.metric}#${n}`]
    }),
  )
}

/** The smallest and largest x over all series (a single x is padded so it sits mid-axis). */
function xDomain(series: readonly MetricSeries[]): [number, number] {
  const xs = series.flatMap((s) => s.points.map((p) => p.x))
  if (xs.length === 0) return [0, 1]
  const min = Math.min(...xs)
  const max = Math.max(...xs)
  return min === max ? [min - 1, max + 1] : [min, max]
}
