/**
 * A searchable grid of line charts, one per metric (Recharts). Generic over the x-axis:
 * the caller says how to label and format x (a version number, a run's start time...).
 *
 * Recharts is large, so pages load this module lazily:
 *   const MetricChartGrid = lazy(() => import('@/components/MetricChartGrid'))
 * and wrap it in `<Suspense>`. Shape the data with `metricSeries` (`@/lib/metric-charts`).
 */
import { useId, useMemo } from 'react'
import { Search } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Input } from '@/components/ui/input'
import { formatMetric } from '@/lib/format'
import { filterMetricSeries, type MetricSeries } from '@/lib/metric-charts'

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

interface MetricChartGridProps {
  series: readonly MetricSeries[]
  xAxis: MetricChartXAxis
  /** The "Search metric charts" text (e.g. from `useChartSearch()`). */
  search: string
  onSearchChange: (search: string) => void
}

export default function MetricChartGrid({ series, xAxis, search, onSearchChange }: MetricChartGridProps) {
  const id = useId()
  const shown = useMemo(() => filterMetricSeries(series, search), [series, search])
  // Every chart spans the same x range, so charts line up when read side by side.
  const domain = useMemo(() => xDomain(series), [series])
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h3 id={id} className="sr-only">
        Metric charts
      </h3>
      <div className="relative w-72 max-w-full">
        <Search aria-hidden className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          aria-label="Search metric charts"
          placeholder="Search metric charts"
          className="pl-8"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      {series.length === 0 ? (
        <p className="text-sm text-muted-foreground">No metrics to chart yet.</p>
      ) : shown.length === 0 ? (
        <p className="text-sm text-muted-foreground">No metric charts match “{search}”.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((s) => (
            <MetricChart key={s.metric} series={s} xAxis={xAxis} domain={domain} />
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
}: {
  series: MetricSeries
  xAxis: MetricChartXAxis
  domain: [number, number]
}) {
  const axisTick = { fontSize: 11, fill: 'var(--muted-foreground)' }
  return (
    <figure className="min-w-0 rounded-lg border p-3">
      <figcaption className="truncate text-xs font-medium" title={series.metric}>
        {series.metric}
      </figcaption>
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
              formatter={(value) => [formatMetric(Number(value)), series.metric]}
              contentStyle={{
                background: 'var(--popover)',
                borderColor: 'var(--border)',
                color: 'var(--popover-foreground)',
                fontSize: 12,
                borderRadius: 6,
              }}
              itemStyle={{ color: 'var(--popover-foreground)' }}
            />
            <Line
              dataKey="value"
              type="linear"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={{ r: 4, fill: 'var(--primary)', stroke: 'var(--card)', strokeWidth: 2 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
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
