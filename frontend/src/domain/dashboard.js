import { withoutNonDiseaseItems } from './displayLabels.js'

const panelKeys = [
  'age',
  'payment',
  'disease_top10',
  'hospital_top10',
  'cost_los_relation',
  'age_severity_matrix',
]

const screenMetricKeys = Object.freeze([
  'record_count',
  'facility_count',
  'avg_los',
  'avg_charges',
  'avg_costs',
  'severe_rate',
])

const ageAliases = {
  '0-17岁': '0 to 17',
  '18-29岁': '18 to 29',
  '30-49岁': '30 to 49',
  '50-69岁': '50 to 69',
  '70岁及以上': '70 or Older',
}

const paymentAliases = {
  'Private Insurance': 'Private Health Insurance',
  Other: 'Miscellaneous/Other',
}

const sectionQuestions = Object.freeze({
  age: '哪个年龄组的病例量最高？',
  payment: '支付方式的病例量如何分布？',
  disease_top10: '哪些疾病的病例量最高？',
  hospital_top10: '哪些医院的病例量最高？',
  cost_los_relation: '住院时长与费用如何关联？',
  age_severity_matrix: '不同年龄组的严重程度如何分布？',
})

export function dashboardSections(payload = {}) {
  const byKey = new Map((payload.sections || []).map(section => [section.key, section]))
  const panels = panelKeys.map(key => {
    const preferredKey = key === 'cost_los_relation' ? 'cost_los_overview' : key
    return withoutNonDiseaseItems(byKey.get(preferredKey) || byKey.get(key))
  }).filter(Boolean)
  return {
    panels,
    correlations: byKey.get('continuous_correlations') || null,
    storage: byKey.get('storage') || null,
  }
}

export function dashboardSectionQuestion(section = {}) {
  return sectionQuestions[section.key]
    || section.visual?.question
    || `${section.title || '当前分析'}呈现什么业务特征？`
}

export function screenMetricSelection(metrics = []) {
  const byKey = new Map(metrics.map(metric => [metric.key, metric]))
  return screenMetricKeys.map(key => byKey.get(key)).filter(Boolean)
}

export function screenSections(payload = {}) {
  const byKey = new Map((payload.sections || []).map(section => [section.key, section]))
  return {
    age: byKey.get('age') || null,
    payment: byKey.get('payment') || null,
    disease: withoutNonDiseaseItems(byKey.get('disease_top10')),
    hospital: byKey.get('hospital_top10') || null,
    relation: byKey.get('cost_los_overview') || byKey.get('cost_los_relation') || null,
    risk: byKey.get('age_severity_matrix') || null,
  }
}

export function screenInsights(payload = {}) {
  return Array.isArray(payload.insights) ? payload.insights : []
}

function publishedValue(items = [], label) {
  return items.find(item => item.label === label)?.value || ''
}

export function drilldownTarget(sectionKey, item = {}, options = {}) {
  if (sectionKey === 'age' || sectionKey === 'age_severity_matrix') {
    const value = ageAliases[item.name || item.x_label] || item.name || item.x_label
    return value ? { path: sectionKey === 'age' ? '/cohorts' : '/risks', query: { age_group: value } } : { path: '/cohorts' }
  }
  if (sectionKey === 'payment') {
    const value = paymentAliases[item.name] || item.name
    return value ? { path: '/payments', query: { payment_type: value } } : { path: '/payments' }
  }
  if (sectionKey === 'disease_top10') {
    const value = publishedValue(options.diagnoses, item.name)
    return value ? { path: '/diseases', query: { diagnosis_code: value } } : { path: '/diseases' }
  }
  if (sectionKey === 'hospital_top10') {
    const value = publishedValue(options.facilities, item.name)
    return value ? { path: '/hospitals', query: { facility_a: value } } : { path: '/hospitals' }
  }
  if (sectionKey === 'cost_los_overview') return { path: '/costs' }
  if (sectionKey === 'cost_los_relation') {
    return item.group && item.group !== '总体' ? { path: '/costs', query: { severity: item.group } } : { path: '/costs' }
  }
  return { path: '/overview' }
}

export function formatGeneratedAt(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export const dashboardPanelKeys = Object.freeze([...panelKeys])
