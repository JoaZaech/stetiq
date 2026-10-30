import { describe, expect, it } from 'vitest'
import { filterMetricSeries, metricSeries } from './metric-charts'

describe('metricSeries', () => {
  it('gives one series per metric, ordered by name, with points ordered along the x-axis', () => {
    const series = metricSeries([
      { x: 3, metrics: { coverage: 0.9, completeness: 1 } },
      { x: 1, metrics: { coverage: 0.5, completeness: 0.25 } },
      { x: 2, metrics: { coverage: 0.75, completeness: 0.5 } },
    ])

    expect(series).toEqual([
      {
        metric: 'completeness',
        points: [
          { x: 1, value: 0.25 },
          { x: 2, value: 0.5 },
          { x: 3, value: 1 },
        ],
      },
      {
        metric: 'coverage',
        points: [
          { x: 1, value: 0.5 },
          { x: 2, value: 0.75 },
          { x: 3, value: 0.9 },
        ],
      },
    ])
  })

  it("leaves a point out of a metric's line when it has no value for that metric", () => {
    const series = metricSeries([
      { x: 1, metrics: { coverage: 0.5 } },
      { x: 2, metrics: {} },
      { x: 3, metrics: { coverage: 1, conformance: 0.8 } },
    ])

    expect(series).toEqual([
      { metric: 'conformance', points: [{ x: 3, value: 0.8 }] },
      {
        metric: 'coverage',
        points: [
          { x: 1, value: 0.5 },
          { x: 3, value: 1 },
        ],
      },
    ])
  })

  it('gives no series when nothing has metrics', () => {
    expect(metricSeries([{ x: 1, metrics: {} }])).toEqual([])
  })
})

describe('filterMetricSeries', () => {
  const series = metricSeries([
    { x: 1, metrics: { 'structural_answerability/answerable': 1, 'coverage/ratio': 0.5 } },
  ])

  it('keeps the charts whose metric name contains the search, ignoring case', () => {
    expect(filterMetricSeries(series, 'ANSWER').map((s) => s.metric)).toEqual([
      'structural_answerability/answerable',
    ])
  })

  it('keeps every chart for a blank search', () => {
    expect(filterMetricSeries(series, '  ')).toHaveLength(2)
  })
})
