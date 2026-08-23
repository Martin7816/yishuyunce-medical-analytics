import { createRouter, createWebHistory } from 'vue-router'

const AnalysisPage = () => import('./views/AnalysisPage.vue')
const OverviewPage = () => import('./views/OverviewPage.vue')
const ModelPage = () => import('./views/ModelPage.vue')
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
const paymentAliases = { 'Private Insurance': 'Private Health Insurance', Other: 'Miscellaneous/Other' }
const linkSources = [
  { endpoint: '/hospitals', option: 'facilities' },
  { endpoint: '/diseases', option: 'diagnoses' },
  { endpoint: '/cohorts/summary', option: 'age_group' },
  { endpoint: '/payments/overview', option: 'payment_type' },
]
const configs = {
  overview: {
    endpoint: '/dashboard/overview', eyebrow: '医院运营概览', clientTitle: '运营总览', clientDescription: '一屏了解住院出院记录的规模、机构、住院时长与费用概况。', clientMetricKeys: ['record_count', 'facility_count', 'avg_los', 'avg_charges', 'avg_costs'], stage: true,
    stageMetricKeys: ['record_count', 'facility_count', 'avg_los', 'avg_charges'], linkSources,
    links: {
      age: { query: 'age_group', requestEndpoint: '/cohorts/summary', endpoint: '/cohorts/summary', aliases: ageAliases },
      payment: { query: 'payment_type', requestEndpoint: '/payments/overview', endpoint: '/payments/overview', aliases: paymentAliases },
      disease_top10: { query: 'diagnosis_code', profilePath: '/diseases/', endpoint: '/diseases', itemField: 'name' },
      hospital_top10: { query: 'facility_a', profilePath: '/hospitals/', endpoint: '/hospitals', itemField: 'name' },
    },
  },
  hospitals: {
    endpoint: '/hospitals', eyebrow: '医院运营对比', clientTitle: '医院运营', clientDescription: '对比各医疗机构的病例量、住院时长与费用结构。', duplicateFilters: ['facility_a', 'facility_b'],
    duplicateMessage: '医院 A 和医院 B 不能选择同一家医院。', highlightMetricKey: 'metric', linkSources: [{ endpoint: '/hospitals', option: 'facilities' }],
    links: {
      ranking: { query: 'facility_a', profilePath: '/hospitals/', endpoint: '/hospitals', itemField: 'name' },
      facility_relation: { query: 'facility_a', profilePath: '/hospitals/', endpoint: '/hospitals', itemField: 'name' },
    },
    filters: [
      { key: 'facility_a', option: 'facilities', label: '医院 A' }, { key: 'facility_b', option: 'facilities', label: '医院 B' },
      { key: 'metric', label: '比较指标', values: comparisonMetricOptions },
    ],
  },
  diseases: {
    endpoint: '/diseases', eyebrow: '疾病结构概览', clientTitle: '疾病分析', clientDescription: '查看主要诊断类别的病例量与住院记录结构。', profile: { key: 'diagnosis_code', path: '/diseases/' }, linkSources: [{ endpoint: '/diseases', option: 'diagnoses' }],
    links: { top10: { query: 'diagnosis_code', profilePath: '/diseases/', endpoint: '/diseases', itemField: 'name' } },
    filters: [{ key: 'diagnosis_code', option: 'diagnoses', label: '疾病' }],
  },
  cohorts: {
    endpoint: '/cohorts/summary', eyebrow: '住院记录群体结构', clientTitle: '群体结构', clientDescription: '按已发布的年龄、性别与入院方式筛选住院记录群体。', layout: 'cohort', alwaysShowClear: true,
    filters: [
      { key: 'age_group', option: 'age_group', label: '年龄组', values: Object.entries(ageAliases).map(([label, value]) => ({ value, label })) },
      { key: 'gender', option: 'gender', label: '性别' }, { key: 'admission_type', option: 'admission_type', label: '入院方式' },
    ],
  },
  costs: {
    endpoint: '/costs/overview', eyebrow: '收费与成本概览', clientTitle: '费用分析', clientDescription: '从收费、成本和住院时长三个维度观察运营结构。', alwaysShowClear: true,
    highlightMetricKeys: ['median_charges', 'p75_charges', 'p90_charges', 'charge_cost_gap'],
    links: { cost_los_relation: { query: 'severity', itemField: 'group' }, severity: { query: 'severity', itemField: 'name' } },
    filters: [
      { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' }, { key: 'facility_id', remote: '/hospitals', option: 'facilities', label: '医院' },
      { key: 'severity', option: 'severity', label: '严重程度', values: severityOptions },
    ], mutuallyExclusive: ['diagnosis_code', 'facility_id'],
  },
  risks: {
    endpoint: '/risks/overview', eyebrow: '严重程度结构', clientTitle: '严重程度', clientDescription: '查看不同住院记录群体的病情严重程度分布。', layout: 'risk', alwaysShowClear: true,
    boundaryNotice: '本页仅展示住院出院记录的群体统计，不构成个人诊断、治疗建议或因果判断。',
    links: {
      age: { query: 'age_group', aliases: ageAliases },
      diseases: { query: 'diagnosis_code', endpoint: '/diseases', itemField: 'name' },
      age_severity_matrix: { query: 'age_group', aliases: ageAliases, itemField: 'x_label' },
    },
    linkSources: [{ endpoint: '/diseases', option: 'diagnoses' }],
    filters: [
      { key: 'age_group', option: 'age_group', label: '年龄组' }, { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' },
    ],
    disclaimer: '群体统计不构成个人诊断、治疗建议或因果判断。',
  },
  payments: {
    endpoint: '/payments/overview', eyebrow: '支付方式结构', clientTitle: '支付方式', clientDescription: '了解不同支付方式下的病例量与平均收费结构。', layout: 'payments', alwaysShowClear: true,
    linkSources: [{ endpoint: '/payments/overview', option: 'payment_type' }],
    links: { payment: { query: 'payment_type', endpoint: '/payments/overview', aliases: paymentAliases } },
    filters: [{ key: 'payment_type', option: 'payment_type', label: '支付方式' }, { key: 'age_group', option: 'age_group', label: '年龄组', values: Object.entries(ageAliases).map(([label, value]) => ({ value, label })) }],
  },
  quality: {
    endpoint: '/data-quality/summary', eyebrow: '数据可用性概览', clientTitle: '数据状态', clientDescription: '快速判断当前分析数据是否完整可用。', layout: 'quality',
    clientMetricKeys: ['raw_rows', 'valid_rows', 'severity_valid_rows', 'severity_missing_rows', 'diagnosis_missing'],
    clientMetricLabels: {
      raw_rows: '住院出院记录', valid_rows: '可用于分析记录', severity_valid_rows: '病情可判定记录',
      severity_missing_rows: '病情待补充记录', diagnosis_missing: '诊断信息缺失记录',
    },
    clientSectionKeys: ['field_missing'], clientSectionTitles: { field_missing: '关键业务字段待补充记录' }, alwaysShowClear: true,
  },
}

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', component: OverviewPage },
  ...[
    ['/hospitals', configs.hospitals], ['/diseases', configs.diseases], ['/cohorts', configs.cohorts],
    ['/costs', configs.costs], ['/risks', configs.risks], ['/payments', configs.payments], ['/data-quality', configs.quality],
  ].map(([path, config]) => ({ path, component: AnalysisPage, props: { config } })),
  { path: '/model', component: ModelPage }, { path: '/assistant', component: AssistantPage },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

export default createRouter({ history: createWebHistory(), routes })
