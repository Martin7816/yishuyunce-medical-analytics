import { createRouter, createWebHistory } from 'vue-router'

const AnalysisPage = () => import('./views/AnalysisPage.vue')
const OverviewPage = () => import('./views/OverviewPage.vue')
const AssistantPage = () => import('./views/AssistantPage.vue')

const comparisonMetricOptions = [
  { value: 'case_count', label: '病例量' }, { value: 'avg_los', label: '平均住院时长' },
  { value: 'avg_charges', label: '平均收费' }, { value: 'avg_costs', label: '平均成本' },
  { value: 'emergency_rate', label: '急诊率' }, { value: 'severe_rate', label: '重症率' },
]
const severityOptions = [
  { value: 'Minor', label: '轻症' }, { value: 'Moderate', label: '中症' },
  { value: 'Major', label: '重症' }, { value: 'Extreme', label: '极重症' },
]
const ageAliases = { '0-17岁': '0 to 17', '18-29岁': '18 to 29', '30-49岁': '30 to 49', '50-69岁': '50 to 69', '70岁及以上': '70 or Older' }
const configs = {
  overview: {
    endpoint: '/dashboard/overview', eyebrow: '医院运营概览', clientTitle: '运营总览', clientDescription: '一屏了解住院出院记录的规模、机构、住院时长与费用概况。', clientMetricKeys: ['record_count', 'facility_count', 'avg_los', 'avg_charges', 'avg_costs'], stage: true,
    stageMetricKeys: ['record_count', 'facility_count', 'avg_los', 'avg_charges'],
  },
  hospitals: {
    endpoint: '/hospitals', eyebrow: '医院运营对比', clientTitle: '医院运营', clientDescription: '对比各医疗机构的病例量、住院时长与费用结构。', duplicateFilters: ['facility_a', 'facility_b'],
    duplicateMessage: '医院 A 和医院 B 不能选择同一家医院。', highlightMetricKey: 'metric',
    filters: [
      { key: 'facility_a', option: 'facilities', label: '医院 A' }, { key: 'facility_b', option: 'facilities', label: '医院 B' },
      { key: 'metric', label: '比较指标', values: comparisonMetricOptions },
    ],
  },
  diseases: {
    endpoint: '/diseases', eyebrow: '疾病结构概览', clientTitle: '疾病分析', clientDescription: '默认查看全部疾病的病例量 TOP10；选择疾病后查看单病种住院记录结构。', clientSectionTitles: { top10: '全部疾病病例量排行（TOP10）' }, profile: { key: 'diagnosis_code', path: '/diseases/' },
    filters: [{ key: 'diagnosis_code', option: 'diagnoses', label: '疾病', allLabel: '全部疾病（展示病例量 TOP10）', quickSection: 'top10', quickLabel: '病例量 TOP10 快捷筛选', help: '点击下方疾病标签可直接筛选；下拉框保留完整疾病列表。' }],
  },
  cohorts: {
    endpoint: '/cohorts/summary', eyebrow: '住院记录群体结构', clientTitle: '群体结构', clientDescription: '按已发布的年龄、性别与入院方式筛选住院记录群体。', layout: 'cohort', alwaysShowClear: true,
    filters: [
      { key: 'age_group', option: 'age_group', label: '年龄组', values: Object.entries(ageAliases).map(([label, value]) => ({ value, label })) },
      { key: 'gender', option: 'gender', label: '性别' }, { key: 'admission_type', option: 'admission_type', label: '入院方式' },
    ],
  },
  costs: {
    endpoint: '/costs/overview', eyebrow: '收费与成本概览', clientTitle: '费用分析', clientDescription: '从收费、成本和住院时长三个维度观察运营结构。', layout: 'costs', alwaysShowClear: true,
    clientMetricKeys: ['record_count', 'avg_charges', 'median_charges', 'p25_charges', 'p75_charges', 'p90_charges', 'avg_costs', 'median_costs', 'p25_costs', 'p75_costs', 'p90_costs', 'charge_cost_gap', 'daily_charges', 'daily_costs'],
    clientMetricLabels: {
      record_count: '住院出院记录', avg_charges: '平均收费', median_charges: '收费 P50', p25_charges: '收费 P25', p75_charges: '收费 P75', p90_charges: '收费 P90',
      avg_costs: '平均成本', median_costs: '成本 P50', p25_costs: '成本 P25', p75_costs: '成本 P75', p90_costs: '成本 P90',
      charge_cost_gap: '平均收费成本差', daily_charges: '日均收费', daily_costs: '日均成本',
    },
    filters: [
      { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' }, { key: 'facility_id', remote: '/hospitals', option: 'facilities', label: '医院' },
      { key: 'severity', option: 'severity', label: '严重程度', values: severityOptions },
    ], mutuallyExclusive: ['diagnosis_code', 'facility_id'],
  },
  risks: {
    endpoint: '/risks/overview', eyebrow: '严重程度结构', clientTitle: '严重程度', clientDescription: '查看不同住院记录群体的病情严重程度分布。', layout: 'risk', alwaysShowClear: true,
    filters: [
      { key: 'age_group', option: 'age_group', label: '年龄组' }, { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' },
    ],
  },
  payments: {
    endpoint: '/payments/overview', eyebrow: '支付方式结构', clientTitle: '支付方式', clientDescription: '了解不同支付方式下的病例量与平均收费结构。', layout: 'payments', alwaysShowClear: true,
    filters: [{ key: 'payment_type', option: 'payment_type', label: '支付方式' }, { key: 'age_group', option: 'age_group', label: '年龄组', values: Object.entries(ageAliases).map(([label, value]) => ({ value, label })) }],
  },
}

function normalizeOverviewRoute(to) {
  if (!Object.prototype.hasOwnProperty.call(to.query, 'mode')) return true
  const query = { ...to.query }
  delete query.mode
  return { path: '/overview', query, replace: true }
}

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', component: OverviewPage, beforeEnter: normalizeOverviewRoute },
  ...[
    ['/hospitals', configs.hospitals], ['/diseases', configs.diseases], ['/cohorts', configs.cohorts],
    ['/costs', configs.costs], ['/risks', configs.risks], ['/payments', configs.payments],
  ].map(([path, config]) => ({ path, component: AnalysisPage, props: { config } })),
  { path: '/model', redirect: '/overview' }, { path: '/assistant', component: AssistantPage },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

export default createRouter({ history: createWebHistory(), routes })
