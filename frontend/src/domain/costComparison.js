export const COST_COMPARISON_DIMENSIONS = Object.freeze([
  { key: 'diagnosis', label: '按疾病' },
  { key: 'facility', label: '按医院' },
  { key: 'severity', label: '按严重程度' },
])

export const COST_COMPARISON_METRICS = Object.freeze([
  { key: 'charges', label: '平均收费' },
  { key: 'costs', label: '平均成本' },
])

export const COST_COMPARISON_SECTION_KEYS = new Set(
  COST_COMPARISON_DIMENSIONS.flatMap(dimension => COST_COMPARISON_METRICS.map(metric => `${dimension.key}_${metric.key}`)),
)

const FILTER_DIMENSION_MAP = Object.freeze({
  diagnosis_code: 'diagnosis',
  facility_id: 'facility',
  severity: 'severity',
})

export function costComparisonDimensionsForFilters(filters = {}) {
  const excludedDimension = Object.entries(FILTER_DIMENSION_MAP)
    .find(([filterKey]) => filters[filterKey])?.[1]

  return COST_COMPARISON_DIMENSIONS.filter(dimension => dimension.key !== excludedDimension)
}

export function costComparisonDimensionForFilters(filters = {}, currentDimension = '') {
  const available = costComparisonDimensionsForFilters(filters)
  return available.some(dimension => dimension.key === currentDimension)
    ? currentDimension
    : available[0]?.key || ''
}
