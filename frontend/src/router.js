import { createRouter, createWebHistory } from 'vue-router'

const AnalysisPage = () => import('./views/AnalysisPage.vue')
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
    endpoint: '/dashboard/overview', eyebrow: '全院运营态势', stage: true,
    stageMetricKeys: ['record_count', 'facility_count', 'avg_los', 'avg_charges'], linkSources,
    links: {
      age: { to: '/cohorts', query: 'age_group', endpoint: '/cohorts/summary', aliases: ageAliases },
      payment: { to: '/payments', query: 'payment_type', endpoint: '/payments/overview', aliases: paymentAliases },
      disease_top10: { to: '/diseases', query: 'diagnosis_code', endpoint: '/diseases', itemField: 'name' },
      hospital_top10: { to: '/hospitals', query: 'facility_a', endpoint: '/hospitals', itemField: 'name' },
    },
  },
  hospitals: {
    endpoint: '/hospitals', eyebrow: '机构横向比较', duplicateFilters: ['facility_a', 'facility_b'],
    duplicateMessage: '医院 A 和医院 B 不能选择同一家医院。', highlightMetricKey: 'metric', linkSources: [{ endpoint: '/hospitals', option: 'facilities' }],
    links: {
      ranking: { to: '/hospitals', query: 'facility_a', endpoint: '/hospitals', itemField: 'name' },
      facility_relation: { to: '/hospitals', query: 'facility_a', endpoint: '/hospitals', itemField: 'name' },
    },
    filters: [
      { key: 'facility_a', option: 'facilities', label: '医院 A' }, { key: 'facility_b', option: 'facilities', label: '医院 B' },
      { key: 'metric', label: '比较指标', values: comparisonMetricOptions },
    ],
  },
  diseases: { endpoint: '/diseases', eyebrow: '疾病群体画像', title: '疾病画像分析', profile: { key: 'diagnosis_code', path: '/diseases/' }, linkSources: [{ endpoint: '/diseases', option: 'diagnoses' }], filters: [{ key: 'diagnosis_code', option: 'diagnoses', label: '疾病' }] },
  cohorts: {
    endpoint: '/cohorts/summary', eyebrow: '有限条件群体切片', title: '住院记录群体分析', layout: 'cohort', alwaysShowClear: true,
    filters: [
      { key: 'age_group', option: 'age_group', label: '年龄组', values: Object.entries(ageAliases).map(([label, value]) => ({ value, label })) },
      { key: 'gender', option: 'gender', label: '性别' }, { key: 'admission_type', option: 'admission_type', label: '入院方式' },
    ],
  },
  costs: {
    endpoint: '/costs/overview', eyebrow: '收费与成本分布', title: '费用与成本分析', alwaysShowClear: true,
    highlightMetricKeys: ['median_charges', 'p75_charges', 'p90_charges', 'charge_cost_gap'],
    links: { cost_los_relation: { to: '/costs', query: 'severity', itemField: 'group' }, severity: { to: '/costs', query: 'severity', itemField: 'name' } },
    filters: [
      { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' }, { key: 'facility_id', remote: '/hospitals', option: 'facilities', label: '医院' },
      { key: 'severity', option: 'severity', label: '严重程度', values: severityOptions },
    ], mutuallyExclusive: ['diagnosis_code', 'facility_id'],
  },
  risks: {
    endpoint: '/risks/overview', eyebrow: '严重程度与风险结构', title: '病情严重程度与风险分析', layout: 'risk', alwaysShowClear: true,
    boundaryNotice: '本页仅展示住院出院记录的群体统计，不构成个人诊断、治疗建议或因果判断。',
    links: {
      age: { to: '/risks', query: 'age_group', aliases: ageAliases },
      diseases: { to: '/risks', query: 'diagnosis_code', endpoint: '/diseases', itemField: 'name' },
      age_severity_matrix: { to: '/risks', query: 'age_group', aliases: ageAliases, itemField: 'x_label' },
    },
    linkSources: [{ endpoint: '/diseases', option: 'diagnoses' }],
    filters: [
      { key: 'age_group', option: 'age_group', label: '年龄组' }, { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' },
    ],
    disclaimer: '群体统计不构成个人诊断、治疗建议或因果判断。',
  },
  payments: {
    endpoint: '/payments/overview', eyebrow: '主支付方式结构', title: '支付方式分析', layout: 'payments', alwaysShowClear: true,
    linkSources: [{ endpoint: '/payments/overview', option: 'payment_type' }],
    links: { payment: { to: '/payments', query: 'payment_type', endpoint: '/payments/overview', aliases: paymentAliases } },
    filters: [{ key: 'payment_type', option: 'payment_type', label: '支付方式' }, { key: 'age_group', option: 'age_group', label: '年龄组', values: Object.entries(ageAliases).map(([label, value]) => ({ value, label })) }],
  },
  quality: { endpoint: '/data-quality/summary', eyebrow: '批次与任务只读状态', title: '数据质量与任务管理', layout: 'quality', alwaysShowClear: true, filters: [{ key: 'data_version', label: '分析批次', valuesFrom: 'data_version', includeAll: false, placeholder: '当前批次' }] },
}

const routes = [
  { path: '/', redirect: '/overview' },
  ...[
    ['/overview', configs.overview], ['/hospitals', configs.hospitals], ['/diseases', configs.diseases], ['/cohorts', configs.cohorts],
    ['/costs', configs.costs], ['/risks', configs.risks], ['/payments', configs.payments], ['/data-quality', configs.quality],
  ].map(([path, config]) => ({ path, component: AnalysisPage, props: { config } })),
  { path: '/model', component: ModelPage }, { path: '/assistant', component: AssistantPage },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

export default createRouter({ history: createWebHistory(), routes })
