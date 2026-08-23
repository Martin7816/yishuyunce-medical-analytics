import test from 'node:test'
import assert from 'node:assert/strict'

import {
  dashboardSectionQuestion,
  dashboardSections,
  drilldownTarget,
  formatGeneratedAt,
  screenInsights,
  screenMetricSelection,
  screenSections,
} from '../src/domain/dashboard.js'
import {
  d3ChartTypes,
  presentationLabel,
  resolveChartPresentation,
} from '../src/domain/chartPresentation.js'

const options = {
  diagnoses: [{ value: 'NVS005', label: 'HEART FAILURE' }],
  facilities: [{ value: '1', label: 'North Shore University Hospital' }],
}

test('dashboardSections exposes the six fixed operating panels and correlation evidence', () => {
  const payload = {
    sections: [
      { key: 'age' }, { key: 'payment' }, { key: 'disease_top10' },
      { key: 'hospital_top10' }, { key: 'cost_los_relation' },
      { key: 'age_severity_matrix' }, { key: 'continuous_correlations' },
    ],
  }

  const result = dashboardSections(payload)

  assert.deepEqual(result.panels.map(section => section.key), [
    'age', 'payment', 'disease_top10', 'hospital_top10',
    'cost_los_relation', 'age_severity_matrix',
  ])
  assert.equal(result.correlations.key, 'continuous_correlations')
})

test('dashboardSectionQuestion exposes a business question for every overview panel', () => {
  assert.equal(
    dashboardSectionQuestion({ key: 'age', title: '年龄结构' }),
    '哪个年龄组的病例量最高？',
  )
  assert.equal(
    dashboardSectionQuestion({ key: 'custom', title: '费用分析' }),
    '费用分析呈现什么业务特征？',
  )
})

test('screen view model selects a concise readout instead of the full workbench payload', () => {
  const metrics = [
    { key: 'record_count', value: 100 },
    { key: 'facility_count', value: 4 },
    { key: 'avg_los', value: 3.2 },
    { key: 'avg_charges', value: 900 },
    { key: 'avg_costs', value: 300 },
    { key: 'severe_rate', value: 0.2 },
    { key: 'extra_metric', value: 999 },
  ]
  const payload = {
    sections: [
      { key: 'age' }, { key: 'payment' }, { key: 'disease_top10' },
      { key: 'hospital_top10' }, { key: 'cost_los_relation' },
      { key: 'age_severity_matrix' }, { key: 'storage' },
    ],
    insights: [{ key: 'cost_los_relation', title: '费用摘要' }],
  }

  assert.deepEqual(screenMetricSelection(metrics).map(metric => metric.key), [
    'record_count', 'facility_count', 'avg_los', 'avg_charges', 'avg_costs', 'severe_rate',
  ])
  assert.deepEqual(Object.keys(screenSections(payload)), [
    'age', 'payment', 'disease', 'hospital', 'relation', 'risk',
  ])
  assert.equal(screenSections(payload).relation.key, 'cost_los_relation')
  assert.equal(screenInsights(payload)[0].title, '费用摘要')
})

test('drilldownTarget only produces published filter values', () => {
  assert.deepEqual(
    drilldownTarget('disease_top10', { name: 'HEART FAILURE' }, options),
    { path: '/diseases', query: { diagnosis_code: 'NVS005' } },
  )
  assert.deepEqual(
    drilldownTarget('hospital_top10', { name: 'North Shore University Hospital' }, options),
    { path: '/hospitals', query: { facility_a: '1' } },
  )
  assert.deepEqual(
    drilldownTarget('age', { name: '50-69岁' }, options),
    { path: '/cohorts', query: { age_group: '50 to 69' } },
  )
  assert.deepEqual(
    drilldownTarget('payment', { name: 'Private Insurance' }, options),
    { path: '/payments', query: { payment_type: 'Private Health Insurance' } },
  )
  assert.deepEqual(
    drilldownTarget('cost_los_relation', { group: 'Major' }, options),
    { path: '/costs', query: { severity: 'Major' } },
  )
})

test('formatGeneratedAt returns a stable Chinese display value and preserves invalid input', () => {
  assert.match(formatGeneratedAt('2026-08-18T08:00:00.000000Z'), /2026/)
  assert.equal(formatGeneratedAt('not-a-date'), 'not-a-date')
  assert.equal(formatGeneratedAt(''), '')
})

test('resolveChartPresentation maps the API contract to controlled D3 SVG charts', () => {
  assert.equal(resolveChartPresentation({ type: 'bar', key: 'payment', items: Array(4) }), 'pie')
  assert.equal(resolveChartPresentation({ type: 'bar', key: 'severity', title: '病情严重程度' }), 'stacked_bar')
  assert.equal(resolveChartPresentation({ type: 'bar', key: 'severity', title: '各严重程度平均成本' }), 'bar')
  assert.equal(resolveChartPresentation({ type: 'bar', key: 'quantiles' }), 'quantile')
  assert.equal(resolveChartPresentation({ type: 'scatter' }), 'scatter')
  assert.equal(resolveChartPresentation({ type: 'heatmap' }), 'heatmap')
  assert.equal(presentationLabel('correlation'), 'D3 相关性分析')
  assert.ok(d3ChartTypes.has('grouped_bar'))
  assert.equal(d3ChartTypes.has('line'), false)
})
