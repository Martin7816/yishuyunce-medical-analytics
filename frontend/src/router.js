import { createRouter, createWebHistory } from 'vue-router'

const AnalysisPage = () => import('./views/AnalysisPage.vue')
const ModelPage = () => import('./views/ModelPage.vue')
const AssistantPage = () => import('./views/AssistantPage.vue')

const configs = {
  overview: { endpoint: '/dashboard/overview', eyebrow: '全院运营态势' },
  hospitals: { endpoint: '/hospitals', eyebrow: '机构横向比较', filters: [
    { key: 'facility_a', option: 'facilities', label: '医院 A' }, { key: 'facility_b', option: 'facilities', label: '医院 B' },
    { key: 'metric', label: '比较指标', values: ['case_count', 'avg_los', 'avg_charges', 'avg_costs', 'emergency_rate', 'severe_rate'] },
  ] },
  diseases: { endpoint: '/diseases', eyebrow: '疾病群体画像', profile: { key: 'diagnosis_code', path: '/diseases/' }, filters: [{ key: 'diagnosis_code', option: 'diagnoses', label: '疾病' }] },
  cohorts: { endpoint: '/cohorts/summary', eyebrow: '有限条件群体切片', filters: [
    { key: 'age_group', option: 'age_group', label: '年龄组' }, { key: 'gender', option: 'gender', label: '性别' }, { key: 'admission_type', option: 'admission_type', label: '入院方式' },
  ] },
  costs: { endpoint: '/costs/overview', eyebrow: '收费与成本分布', filters: [
    { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' }, { key: 'facility_id', remote: '/hospitals', option: 'facilities', label: '医院' }, { key: 'severity', option: 'severity', label: '严重程度' },
  ], mutuallyExclusive: ['diagnosis_code', 'facility_id'] },
  risks: { endpoint: '/risks/overview', eyebrow: '严重程度与风险结构', filters: [
    { key: 'age_group', option: 'age_group', label: '年龄组' }, { key: 'diagnosis_code', remote: '/diseases', option: 'diagnoses', label: '疾病' },
  ], disclaimer: '群体统计不构成个人诊断、治疗建议或因果判断。' },
  payments: { endpoint: '/payments/overview', eyebrow: '主支付方式结构', filters: [
    { key: 'payment_type', option: 'payment_type', label: '支付方式' }, { key: 'age_group', option: 'age_group', label: '年龄组' },
  ] },
  quality: { endpoint: '/data-quality/summary', eyebrow: '批次与任务只读状态' },
}

const routes = [
  { path: '/', redirect: '/overview' },
  ...[
    ['/overview', configs.overview], ['/hospitals', configs.hospitals], ['/diseases', configs.diseases],
    ['/cohorts', configs.cohorts], ['/costs', configs.costs], ['/risks', configs.risks],
    ['/payments', configs.payments], ['/data-quality', configs.quality],
  ].map(([path, config]) => ({ path, component: AnalysisPage, props: { config } })),
  { path: '/model', component: ModelPage }, { path: '/assistant', component: AssistantPage },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

export default createRouter({ history: createWebHistory(), routes })
