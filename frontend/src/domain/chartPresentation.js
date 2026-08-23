const STRUCTURE_KEYS = new Set(['gender', 'medical_surgical', 'disposition'])
const STACKED_KEYS = new Set(['severity', 'mortality'])
const COST_TITLE_PATTERN = /(平均收费|平均成本|收费|成本)/

export const d3ChartTypes = new Set([
  'bar', 'pie', 'grouped_bar', 'scatter', 'heatmap', 'correlation',
])

export function resolveChartPresentation(section = {}) {
  if (section.type !== 'bar') return section.type

  const key = section.key
  const title = section.title || ''
  const itemCount = section.items?.length || 0

  if (key === 'quantiles') return 'quantile'
  if (STRUCTURE_KEYS.has(key)) return 'pie'
  if (key === 'payment' && itemCount <= 5) return 'pie'
  if (STACKED_KEYS.has(key) && !COST_TITLE_PATTERN.test(title)) return 'stacked_bar'
  return 'bar'
}

export function presentationLabel(presentation) {
  return {
    bar: 'D3 类别排行',
    pie: 'D3 结构占比',
    stacked_bar: 'D3 结构占比',
    quantile: 'D3 费用分位点',
    grouped_bar: 'D3 对象对照',
    scatter: 'D3 关系探索',
    heatmap: 'D3 二维结构',
    correlation: 'D3 相关性分析',
  }[presentation] || '数据明细'
}
