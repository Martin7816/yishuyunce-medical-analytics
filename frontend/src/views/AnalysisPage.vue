<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiRequest, isAbortError, withQuery } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'
import RankingVisual from '../components/RankingVisual.vue'
import RiskDistributionChart from '../components/RiskDistributionChart.vue'
import {
  displayMetricLabel,
  displayOptionLabel,
  displaySectionItemValue,
  displayText,
  isNonDiseaseLabel,
  withoutNonDiseaseItems,
} from '../domain/displayLabels.js'
import { prepareFilterNavigation, queryForFilters } from '../domain/filterNavigation.js'
import { optionsForSection } from '../domain/filterOptions.js'
import { filterSectionsByActiveFilters } from '../domain/sectionVisibility.js'
import {
  COST_COMPARISON_DIMENSIONS,
  COST_COMPARISON_METRICS,
  COST_COMPARISON_SECTION_KEYS,
  costComparisonDimensionForFilters,
  costComparisonDimensionsForFilters,
} from '../domain/costComparison.js'

const costPrimaryMetricKeys = Object.freeze([
  'record_count',
  'avg_charges',
  'avg_costs',
  'charge_cost_gap',
])

const costMetricGroupDefinitions = Object.freeze([
  {
    key: 'charges',
    title: '收费分布',
    description: 'P25 / P50 / P75 / P90',
    metricKeys: ['p25_charges', 'median_charges', 'p75_charges', 'p90_charges'],
  },
  {
    key: 'costs',
    title: '成本分布',
    description: 'P25 / P50 / P75 / P90',
    metricKeys: ['p25_costs', 'median_costs', 'p75_costs', 'p90_costs'],
  },
  {
    key: 'efficiency',
    title: '日均水平',
    description: '收费与成本按天比较',
    metricKeys: ['daily_charges', 'daily_costs'],
  },
])

const costComparisonDimensions = COST_COMPARISON_DIMENSIONS
const costComparisonMetrics = COST_COMPARISON_METRICS
const costComparisonSectionKeys = COST_COMPARISON_SECTION_KEYS
const riskDistributionSectionKeys = Object.freeze(['severity', 'mortality'])
const riskDetailSectionKeys = Object.freeze(['disposition', 'age_severity_matrix'])
const riskContextSectionKeys = Object.freeze(['age', 'diseases'])
const riskSectionKeys = new Set([
  ...riskDistributionSectionKeys,
  ...riskDetailSectionKeys,
  ...riskContextSectionKeys,
])
const rankingVisualSectionKeys = new Set(['procedures', 'hospitals'])
const riskSecondaryMetricKeys = Object.freeze([
  'severity_valid_count',
  'high_risk_count',
  'avg_los',
  'avg_charges',
  'avg_costs',
])

const props = defineProps({ config: { type: Object, required: true } })
const route = useRoute()
const router = useRouter()
const state = ref('loading')
const data = ref(null)
const error = ref(null)
const validationMessage = ref('')
const filters = reactive({})
const optionSets = reactive({})
const fullscreen = ref(false)
const fullscreenError = ref('')
const routeQueryMessage = ref('')

let requestId = 0
let activeController = null
let debounceTimer
const remoteOptionsCache = new Map()

const isStage = computed(() => Boolean(props.config.stage && route.query.mode === 'screen'))
const hasActiveFilter = computed(() => Object.values(filters).some(value => value !== '' && value != null))
const isFixture = computed(() => {
  const dataVersion = data.value?.filters?.data_version || data.value?.data_version || ''
  return dataVersion.startsWith('fixture:')
})
const mutuallyExclusiveMessage = computed(() => props.config.mutuallyExclusive?.length
  ? '疾病与医院筛选互斥；选择其中一项后，另一项会暂时停用。'
  : '')
const usePlainMetricNumbers = computed(() => ['cohort', 'costs'].includes(props.config.layout))
const visibleMetrics = computed(() => {
  const metrics = data.value?.metrics || []
  const keys = isStage.value ? props.config.stageMetricKeys : props.config.clientMetricKeys
  const visible = keys?.length ? metrics.filter(metric => keys.includes(metric.key)) : metrics
  const labels = props.config.clientMetricLabels || {}
  return visible.map(metric => ({
    ...metric,
    label: displayText(labels[metric.key] || displayMetricLabel(metric)),
  }))
})
const riskLeadMetric = computed(() => props.config.layout === 'risk'
  ? visibleMetrics.value.find(metric => metric.key === 'high_risk_rate') || null
  : null)
const riskSecondaryMetrics = computed(() => {
  if (props.config.layout !== 'risk') return []
  const byKey = new Map(visibleMetrics.value.map(metric => [metric.key, metric]))
  return riskSecondaryMetricKeys.map(key => byKey.get(key)).filter(Boolean)
})
const riskHeroNote = computed(() => {
  if (!riskLeadMetric.value) return ''
  const byKey = new Map(visibleMetrics.value.map(metric => [metric.key, metric]))
  const count = byKey.get('high_risk_count')?.value
  const total = byKey.get('severity_valid_count')?.value
  if (typeof count !== 'number' || typeof total !== 'number') return '重症 / 极重症记录占当前可判定严重程度记录的比例。'
  const format = value => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false }).format(value)
  return `重症 / 极重症记录 ${format(count)} 条，占可判定严重程度记录的 ${format((count / total) * 100)}%。`
})
const costsPrimaryMetrics = computed(() => {
  const byKey = new Map(visibleMetrics.value.map(metric => [metric.key, metric]))
  return costPrimaryMetricKeys.map(key => byKey.get(key)).filter(Boolean)
})
const costsMetricGroups = computed(() => {
  const byKey = new Map(visibleMetrics.value.map(metric => [metric.key, metric]))
  return costMetricGroupDefinitions
    .map(group => ({ ...group, metrics: group.metricKeys.map(key => byKey.get(key)).filter(Boolean) }))
    .filter(group => group.metrics.length)
})
const costComparisonDimension = ref('diagnosis')
const costComparisonMetric = ref('charges')
const costNumberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false })
const visibleCostComparisonDimensions = computed(() => costComparisonDimensionsForFilters({
  diagnosis_code: filters.diagnosis_code,
  facility_id: filters.facility_id,
  severity: filters.severity,
}))
const activeCostComparisonDimension = computed(() => costComparisonDimensionForFilters({
  diagnosis_code: filters.diagnosis_code,
  facility_id: filters.facility_id,
  severity: filters.severity,
}, costComparisonDimension.value))

function formatCostMetric(metric) {
  if (metric.value == null) return '—'
  if (typeof metric.value !== 'number') return metric.value
  if (metric.unit === '%') return `${costNumberFormatter.format(metric.value * 100)}%`
  return costNumberFormatter.format(metric.value)
}

function formatCostMetricUnit(metric) {
  return metric.key === 'record_count' ? metric.unit : ''
}

function isCostRedundantSection(section) {
  if (props.config.layout !== 'costs') return false
  const key = String(section.key || '').toLowerCase()
  return key === 'quantiles'
    || key === 'charges_quantiles'
    || key === 'costs_quantiles'
    || key === 'charge_cost_distribution'
    || String(section.title || '').includes('分位数')
    || String(section.title || '').includes('收费与成本分布')
}

const visibleSections = computed(() => {
  const sections = data.value?.sections || []
  const visible = props.config.clientSectionKeys?.length
    ? sections.filter(section => props.config.clientSectionKeys.includes(section.key))
    : sections
  const titles = props.config.clientSectionTitles || {}
  return filterSectionsByActiveFilters(visible, filters)
    .filter(section => !isCostRedundantSection(section))
    .map(section => withoutNonDiseaseItems(titles[section.key] ? { ...section, title: titles[section.key] } : section))
})
const costComparisonSections = computed(() => props.config.layout === 'costs'
  ? visibleSections.value.filter(section => costComparisonSectionKeys.has(section.key))
  : [])
function orderedRiskSections(keys) {
  const byKey = new Map(visibleSections.value.map(section => [section.key, section]))
  return keys.map(key => byKey.get(key)).filter(Boolean)
}
const riskDistributionSections = computed(() => props.config.layout === 'risk'
  ? orderedRiskSections(riskDistributionSectionKeys)
  : [])
const riskDetailSections = computed(() => props.config.layout === 'risk'
  ? orderedRiskSections(riskDetailSectionKeys)
  : [])
const riskContextSections = computed(() => props.config.layout === 'risk'
  ? orderedRiskSections(riskContextSectionKeys)
  : [])
const activeCostComparisonSection = computed(() => {
  const requestedKey = `${activeCostComparisonDimension.value}_${costComparisonMetric.value}`
  return costComparisonSections.value.find(section => section.key === requestedKey)
    || costComparisonSections.value.find(section => section.key.startsWith(`${activeCostComparisonDimension.value}_`))
    || costComparisonSections.value[0]
    || null
})
const renderableVisibleSections = computed(() => props.config.layout === 'costs'
  ? visibleSections.value.filter(section => !costComparisonSectionKeys.has(section.key))
  : props.config.layout === 'risk'
    ? visibleSections.value.filter(section => !riskSectionKeys.has(section.key))
    : visibleSections.value)
const orderedVisibleSections = computed(() => {
  if (props.config.endpoint !== '/hospitals') return renderableVisibleSections.value
  const order = ['ranking', 'facility_metric_comparison', 'facility_relation']
  const byKey = new Map(renderableVisibleSections.value.map(section => [section.key, section]))
  return [
    ...order.map(key => byKey.get(key)).filter(Boolean),
    ...renderableVisibleSections.value.filter(section => !order.includes(section.key)),
  ]
})
const comparisonProfiles = computed(() => (data.value?.comparison || []).map(profile => ({
  ...profile,
  sections: (profile.sections || []).map(withoutNonDiseaseItems),
})))
const isHospitalSelectionActive = computed(() => props.config.endpoint === '/hospitals'
  && Boolean(filters.facility_a || filters.facility_b))

function isDiseaseRankingVisual(section) {
  return props.config.endpoint === '/diseases' && rankingVisualSectionKeys.has(section.key)
}

function isCohortSeverityVisual(section) {
  return props.config.layout === 'cohort' && section.key === 'severity'
}

function isInlineRiskDistribution(section) {
  return isCohortSeverityVisual(section)
    || props.config.endpoint === '/diseases' && riskDistributionSectionKeys.includes(section.key)
    || props.config.endpoint === '/hospitals' && section.key === 'severity'
}

function distributionKicker(section) {
  return section.key === 'mortality' ? '风险分层' : '病情分层'
}

function distributionTitle(section) {
  return section.key === 'mortality' ? '死亡风险分布' : '严重程度分布'
}

function distributionSection(section) {
  return { ...section, title: distributionTitle(section) }
}

function normalizeOptions(values = [], context = '') {
  return values.filter(value => value != null).filter(item => {
    if (context !== 'diagnosis_code') return true
    const option = typeof item === 'object' ? item : { value: item, label: item }
    return !isNonDiseaseLabel(option.value) && !isNonDiseaseLabel(option.label)
  }).map(item => {
    const option = typeof item === 'object' ? item : { value: item, label: item }
    const value = option.value ?? option.label
    const rawLabel = option.rawLabel ?? option.label ?? value
    const label = displayOptionLabel(context, rawLabel, value)
    return { ...option, value, rawLabel, label }
  })
}

const quickFilterGroups = computed(() => (props.config.filters || [])
  .filter(filter => filter.quickSection)
  .map(filter => ({
    ...filter,
    options: optionsForSection(optionSets[filter.key] || [], data.value, filter.quickSection),
  }))
  .filter(group => group.options.length))

function queryValue(query, key) {
  const value = query[key]
  return Array.isArray(value) ? (typeof value[0] === 'string' ? value[0] : '') : (typeof value === 'string' ? value : '')
}

function allowedQuery(values = filters) {
  return queryForFilters(props.config, values, route.query)
}

function syncFiltersFromRoute() {
  let changed = false
  const allowed = new Set((props.config.filters || []).map(filter => filter.key))
  for (const filter of props.config.filters || []) {
    const next = queryValue(route.query, filter.key)
    if (filters[filter.key] !== next) { filters[filter.key] = next; changed = true }
  }
  const unknownKeys = Object.keys(route.query).filter(key => !allowed.has(key) && key !== 'mode')
  const invalidMode = Object.prototype.hasOwnProperty.call(route.query, 'mode')
    && (!props.config.stage || route.query.mode !== 'screen')
  routeQueryMessage.value = unknownKeys.length || invalidMode
    ? `当前链接包含不支持的参数：${[...unknownKeys, ...(invalidMode ? ['mode'] : [])].join('、')}。请清除参数后重试。`
    : ''
  return changed
}

function duplicateSelectionMessage() {
  const keys = props.config.duplicateFilters || []
  if (keys.length < 2) return ''
  const values = keys.map(key => filters[key]).filter(Boolean)
  return values.length === keys.length && new Set(values).size !== values.length
    ? props.config.duplicateMessage || '筛选条件不能选择相同的对象。'
    : ''
}

function clearActiveRequest() {
  requestId += 1
  activeController?.abort()
  activeController = null
}

function setLocalOptions(payload) {
  for (const filter of props.config.filters || []) {
    let values = filter.values
    if (filter.valuesFrom === 'data_version' && (payload?.data_version || payload?.filters?.data_version)) values = [payload.filters?.data_version || payload.data_version]
    if (!filter.remote && !values) values = payload?.options?.[filter.option]
    if (values) {
      optionSets[filter.key] = normalizeOptions(values, filter.key)
    }
  }
}

async function loadRemoteOptions(current, signal) {
  const remotes = new Map()
  for (const filter of props.config.filters || []) {
    if (!filter.remote) continue
    if (!remotes.has(filter.remote)) remotes.set(filter.remote, [])
    remotes.get(filter.remote).push(filter)
  }
  await Promise.all([...remotes.entries()].map(async ([remote, remoteFilters]) => {
    let payload = remoteOptionsCache.get(remote)
    if (!payload) {
      payload = await apiRequest(remote, { signal })
      if (current !== requestId) return
      remoteOptionsCache.set(remote, payload)
    }
    if (current !== requestId) return
    for (const filter of remoteFilters) optionSets[filter.key] = normalizeOptions(payload?.options?.[filter.option], filter.key)
  }))

}

function hasContent(payload) {
  return Boolean(payload?.metrics?.length || payload?.sections?.some(section => section.items?.length))
}

async function load() {
  if (routeQueryMessage.value) {
    clearActiveRequest(); data.value = null; error.value = null; validationMessage.value = routeQueryMessage.value; state.value = 'validation'; return
  }
  const invalidSelection = duplicateSelectionMessage()
  if (invalidSelection) {
    clearActiveRequest(); data.value = null; error.value = null; validationMessage.value = invalidSelection; state.value = 'validation'; return
  }
  validationMessage.value = ''
  const current = ++requestId
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  state.value = 'loading'; data.value = null; error.value = null
  try {
    await loadRemoteOptions(current, controller.signal)
    if (current !== requestId) return
    let path = props.config.endpoint
    if (props.config.profile && filters[props.config.profile.key]) path = `${props.config.profile.path}${encodeURIComponent(filters[props.config.profile.key])}`
    else path = withQuery(path, filters)
    const payload = await apiRequest(path, { signal: controller.signal })
    if (current !== requestId) return
    data.value = payload; setLocalOptions(payload); state.value = hasContent(payload) ? 'success' : 'empty'
  } catch (caught) {
    if (current !== requestId || controller.signal.aborted || isAbortError(caught)) return
    error.value = caught; state.value = 'error'
  } finally {
    if (current === requestId && activeController === controller) activeController = null
  }
}

function scheduleLoad() {
  clearTimeout(debounceTimer)
  const invalidSelection = duplicateSelectionMessage()
  if (invalidSelection) { clearActiveRequest(); data.value = null; error.value = null; validationMessage.value = invalidSelection; state.value = 'validation'; return }
  validationMessage.value = ''
  debounceTimer = setTimeout(load, 180)
}

function updateFilter(key, value) {
  const navigation = prepareFilterNavigation(filters, props.config, key, value, route.query)
  if (navigation.shouldLoad) {
    router.push({ query: navigation.query })
  } else {
    Object.assign(filters, navigation.values)
    scheduleLoad()
  }
}

function isFilterDisabled(filter) {
  const mutuallyExclusive = props.config.mutuallyExclusive || []
  return mutuallyExclusive.includes(filter.key) && mutuallyExclusive.some(key => key !== filter.key && filters[key])
}

function clearFilters() {
  const nextQuery = allowedQuery({})
  if (JSON.stringify(nextQuery) === JSON.stringify(route.query)) {
    for (const filter of props.config.filters || []) filters[filter.key] = ''
    scheduleLoad()
  }
  else {
    router.push({ query: nextQuery })
  }
}

function clearInvalidQuery() {
  if (duplicateSelectionMessage()) {
    clearFilters()
    return
  }
  router.replace({ query: allowedQuery() })
}

function setStage(value) {
  const nextQuery = { ...route.query }
  if (value) nextQuery.mode = 'screen'
  else delete nextQuery.mode
  router.push({ query: nextQuery })
}

async function toggleFullscreen() {
  fullscreenError.value = ''
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await document.documentElement.requestFullscreen()
  } catch {
    fullscreenError.value = '浏览器未允许全屏，请使用浏览器菜单或继续使用大屏布局。'
  }
}

function onFullscreenChange() { fullscreen.value = Boolean(document.fullscreenElement) }

function isMetricHighlighted(metric) {
  return Boolean(props.config.highlightMetricKeys?.includes(metric.key)
    || props.config.highlightMetricKey && filters[props.config.highlightMetricKey] === metric.key)
}

watch(() => props.config, () => {
  clearTimeout(debounceTimer); clearActiveRequest(); remoteOptionsCache.clear()
  for (const key of Object.keys(filters)) delete filters[key]
  for (const key of Object.keys(optionSets)) delete optionSets[key]
  for (const filter of props.config.filters || []) filters[filter.key] = ''
  syncFiltersFromRoute(); data.value = null; error.value = null; validationMessage.value = ''; load()
}, { immediate: true })

watch(() => route.fullPath, () => {
  const changed = syncFiltersFromRoute()
  if (changed || routeQueryMessage.value || state.value === 'validation') load()
})

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange))
onBeforeUnmount(() => { clearTimeout(debounceTimer); clearActiveRequest(); document.removeEventListener('fullscreenchange', onFullscreenChange) })
</script>

<template>
  <div class="page-wrap" :class="{ 'screen-mode': isStage, 'costs-page': config.layout === 'costs' }" :aria-busy="state === 'loading'">
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ config.eyebrow }}</p>
         <h1 id="page-title" data-page-title tabindex="-1">{{ config.clientTitle || data?.title || config.title || '医数云策分析模块' }}</h1>
          <p id="page-description">{{ displayText(config.clientDescription || data?.description || '正在读取分析数据。') }}</p>
       </div>
       <div class="heading-actions">
         <button v-if="config.stage" type="button" class="secondary-button" @click="setStage(!isStage)">{{ isStage ? '退出大屏' : '大屏演示' }}</button>
         <button v-if="isStage" type="button" class="secondary-button" @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '浏览器全屏' }}</button>
       </div>
     </header>
     <p v-if="fullscreenError" class="filter-notice" role="alert">{{ fullscreenError }}</p>
     <fieldset v-if="config.filters?.length" class="filter-bar">
       <legend class="filter-legend">筛选条件</legend>
      <label v-for="filter in config.filters" :key="filter.key" :for="`filter-${filter.key}`">
         {{ displayText(filter.label) }}
        <select :id="`filter-${filter.key}`" :value="filters[filter.key] || ''" :aria-label="filter.label" :aria-describedby="[isFilterDisabled(filter) ? 'filter-help' : '', filter.help ? `filter-help-${filter.key}` : ''].filter(Boolean).join(' ') || undefined" :disabled="isFilterDisabled(filter)" @change="updateFilter(filter.key, $event.target.value)">
          <option value="">{{ filter.includeAll === false ? (filter.placeholder || '请选择') : (filter.allLabel || '全部') }}</option>
          <option v-for="item in optionSets[filter.key]" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <template v-for="group in quickFilterGroups" :key="`quick-filter-${group.key}`">
        <div class="quick-filter-group">
          <span class="quick-filter-label">{{ displayText(group.quickLabel || '快捷筛选') }}</span>
          <div class="quick-filter-options" role="group" :aria-label="displayText(group.quickLabel || `${group.label}快捷筛选`)">
            <button
              v-for="item in group.options"
              :key="item.value"
              type="button"
              class="quick-filter-button"
              :class="{ active: filters[group.key] === item.value }"
              :aria-pressed="filters[group.key] === item.value"
              :aria-label="`按${item.label}筛选`"
              @click="updateFilter(group.key, item.value)"
            >
              <span>{{ item.label }}</span>
            </button>
          </div>
        </div>
      </template>
      <button v-if="config.alwaysShowClear || hasActiveFilter || validationMessage" type="button" class="secondary-button" @click="clearFilters">清空筛选</button>
      <template v-for="filter in config.filters" :key="`filter-help-${filter.key}`">
        <p v-if="filter.help" :id="`filter-help-${filter.key}`" class="filter-help">{{ displayText(filter.help) }}</p>
      </template>
      <p v-if="mutuallyExclusiveMessage" id="filter-help" class="filter-help">{{ mutuallyExclusiveMessage }}</p>
    </fieldset>
    <p v-if="validationMessage && state !== 'validation'" class="filter-notice" role="alert">{{ validationMessage }}</p>
     <p v-if="isFixture" class="warning-note" role="note">当前为演示数据，数值仅用于展示分析功能；正式业务结论请以正式数据为准。</p>

    <PageState v-if="state !== 'success'" :state="state" :error="error" :message="validationMessage" @retry="load" @clear="clearInvalidQuery" />
    <template v-else-if="state === 'success'">
      <section v-if="config.layout === 'costs'" class="costs-metrics" aria-labelledby="costs-metrics-title">
        <div class="costs-metrics-heading">
          <h2 id="costs-metrics-title">费用与成本指标</h2>
          <span class="costs-unit-note">金额单位：美元</span>
        </div>
        <div class="costs-summary" role="list" aria-label="费用页关键指标">
          <div v-for="item in costsPrimaryMetrics" :key="`cost-primary-${item.key}`" class="costs-summary-item" role="listitem">
            <span class="costs-summary-label">{{ item.label }}</span>
            <div class="costs-summary-value">
              <strong>{{ formatCostMetric(item) }}</strong>
              <small v-if="formatCostMetricUnit(item)">{{ formatCostMetricUnit(item) }}</small>
            </div>
          </div>
        </div>
        <div class="costs-detail-heading">
          <h3>指标明细</h3>
        </div>
        <div class="costs-reading-grid">
          <section v-for="group in costsMetricGroups" :key="group.key" class="costs-reading-group">
            <header class="costs-group-heading">
              <h3>{{ group.title }}</h3>
              <p>{{ group.description }}</p>
            </header>
            <dl class="costs-detail-list">
              <div v-for="item in group.metrics" :key="`cost-${group.key}-${item.key}`" class="costs-detail-row">
                <dt>{{ item.label }}</dt>
                <dd>
                  <strong>{{ formatCostMetric(item) }}</strong>
                </dd>
              </div>
            </dl>
          </section>
        </div>
      </section>
      <section v-else-if="config.layout === 'risk'" class="risk-overview" aria-labelledby="risk-overview-title">
        <div class="risk-overview-lead">
          <div class="risk-overview-heading">
            <div>
              <p class="eyebrow">风险结论</p>
              <h2 id="risk-overview-title">当前筛选范围的高风险概览</h2>
            </div>
            <span>重症 / 极重症</span>
          </div>
          <MetricCard v-if="riskLeadMetric" class="risk-lead-metric" :metric="riskLeadMetric" />
          <p class="risk-overview-note">{{ riskHeroNote }}</p>
        </div>
        <div class="risk-secondary-metrics" role="list" aria-label="高风险群体关键指标">
          <MetricCard v-for="item in riskSecondaryMetrics" :key="`risk-summary-${item.key}`" :metric="item" role="listitem" />
        </div>
      </section>
      <section v-else-if="!isHospitalSelectionActive" class="metric-grid" :class="{ 'stage-metric-grid': isStage }">
        <MetricCard v-for="item in visibleMetrics" :key="item.key" :metric="item" :plain-number="usePlainMetricNumbers" :highlighted="isMetricHighlighted(item)" />
      </section>
      <template v-if="comparisonProfiles.length">
        <section class="comparison-grid" :class="{ 'comparison-grid--single': comparisonProfiles.length === 1 }" aria-label="医院运营画像">
          <article v-for="(profile, profileIndex) in comparisonProfiles" :key="`comparison-${profileIndex}`" class="content-card comparison-card">
             <h2>{{ displayText(profile.title) }}</h2><p v-if="profile.description" class="profile-description">{{ displayText(profile.description) }}</p>
            <div class="compact-metrics"><MetricCard v-for="item in profile.metrics" :key="item.key" :metric="item" :plain-number="usePlainMetricNumbers" :highlighted="isMetricHighlighted(item)" /></div>
             <div v-if="profile.sections?.length" class="profile-section-grid">
              <section
                v-for="(section, sectionIndex) in profile.sections"
                :key="`${profileIndex}-${section.key}-${sectionIndex}`"
                class="profile-section"
                :class="{ 'risk-distribution-panel': isInlineRiskDistribution(section), 'inline-risk-distribution-card': isInlineRiskDistribution(section) }"
              >
                <template v-if="isInlineRiskDistribution(section)">
                  <div class="risk-panel-heading">
                    <div>
                      <span class="risk-panel-kicker">{{ distributionKicker(section) }}</span>
                      <h3>{{ distributionTitle(section) }}</h3>
                    </div>
                    <span>按等级</span>
                  </div>
                  <RiskDistributionChart :section="distributionSection(section)" :selectable="false" />
                </template>
                <template v-else>
                  <h3>{{ displayText(section.title) }}</h3>
                  <AnalyticsChart :section="section" :selectable="false" />
                </template>
              </section>
            </div>
          </article>
        </section>
      </template>
      <section v-if="config.layout === 'costs' && activeCostComparisonSection" class="cost-comparison-workspace content-card" aria-labelledby="cost-comparison-title">
        <div class="cost-comparison-heading">
          <div>
            <p class="eyebrow">费用对比</p>
            <h2 id="cost-comparison-title">费用对比分析</h2>
            <p>选择一个比较维度和指标，查看当前筛选结果中的主要项目。</p>
          </div>
          <span class="cost-comparison-current" aria-live="polite">{{ displayText(activeCostComparisonSection.title) }}</span>
        </div>
        <div class="cost-comparison-controls">
          <div class="cost-comparison-control">
            <span class="cost-comparison-control-label">比较维度</span>
            <div class="cost-comparison-tabs" role="tablist" aria-label="费用比较维度">
              <button
                v-for="option in visibleCostComparisonDimensions"
                :key="`cost-dimension-${option.key}`"
                type="button"
                class="cost-comparison-tab"
                :class="{ active: activeCostComparisonDimension === option.key }"
                role="tab"
                :aria-selected="activeCostComparisonDimension === option.key"
                @click="costComparisonDimension = option.key"
              >{{ option.label }}</button>
            </div>
          </div>
          <div class="cost-comparison-control">
            <span class="cost-comparison-control-label">比较指标</span>
            <div class="cost-comparison-tabs" role="tablist" aria-label="费用比较指标">
              <button
                v-for="option in costComparisonMetrics"
                :key="`cost-metric-${option.key}`"
                type="button"
                class="cost-comparison-tab"
                :class="{ active: costComparisonMetric === option.key }"
                role="tab"
                :aria-selected="costComparisonMetric === option.key"
                @click="costComparisonMetric = option.key"
              >{{ option.label }}</button>
            </div>
          </div>
        </div>
        <div class="cost-comparison-chart" role="tabpanel" aria-live="polite">
          <div class="cost-comparison-chart-heading">
            <div>
              <h3>{{ displayText(activeCostComparisonSection.title) }}</h3>
              <p>按数值从高到低排序，展示当前结果中的主要项目。</p>
            </div>
          </div>
          <AnalyticsChart :section="activeCostComparisonSection" :show-summary="false" :selectable="false" />
        </div>
      </section>
      <template v-if="config.layout === 'risk'">
        <section v-if="riskDistributionSections.length" class="risk-distribution-card content-card" aria-labelledby="risk-distribution-title">
          <header class="risk-block-heading">
              <div>
                <p class="eyebrow">核心分布</p>
                <h2 id="risk-distribution-title">严重程度与死亡风险</h2>
              </div>
            <span>群体统计 · 单位：条</span>
          </header>
          <div class="risk-distribution-grid">
            <article v-for="section in riskDistributionSections" :key="`risk-distribution-${section.key}`" class="risk-distribution-panel">
              <div class="risk-panel-heading">
                <div>
                  <span class="risk-panel-kicker">{{ section.key === 'mortality' ? '风险分层' : '病情分层' }}</span>
                  <h3>{{ displayText(section.title) }}</h3>
                </div>
                <span>按等级</span>
              </div>
              <RiskDistributionChart :section="section" :selectable="false" />
            </article>
          </div>
        </section>
        <section v-if="riskDetailSections.length" class="risk-detail-card content-card" aria-labelledby="risk-detail-title">
          <header class="risk-block-heading">
            <div>
              <p class="eyebrow">进一步定位</p>
              <h2 id="risk-detail-title">高风险记录画像</h2>
              <p>结合年龄结构、病情等级和离院去向，帮助判断风险主要集中在哪里。</p>
            </div>
          </header>
          <div class="risk-detail-grid">
            <article v-for="section in riskDetailSections" :key="`risk-detail-${section.key}`" class="risk-detail-panel" :class="{ 'risk-detail-panel--matrix': section.key === 'age_severity_matrix' }">
              <div class="risk-panel-heading">
                <h3>{{ displayText(section.title) }}</h3>
                <span>{{ section.key === 'age_severity_matrix' ? '交叉结构' : '记录去向' }}</span>
              </div>
              <AnalyticsChart :section="section" :compact="true" :selectable="false" :show-details="section.key !== 'disposition'" />
            </article>
          </div>
        </section>
        <section v-if="riskContextSections.length" class="risk-context-card content-card" aria-labelledby="risk-context-title">
          <header class="risk-block-heading">
            <div>
              <p class="eyebrow">筛选背景</p>
              <h2 id="risk-context-title">当前群体结构</h2>
              <p>年龄和疾病仅作为当前筛选范围的背景信息展示。</p>
            </div>
          </header>
          <div class="risk-context-grid">
            <article v-for="section in riskContextSections" :key="`risk-context-${section.key}`" class="risk-context-panel">
              <div class="risk-panel-heading">
                <h3>{{ displayText(section.title) }}</h3>
                <span>筛选背景</span>
              </div>
              <div v-if="section.items?.length === 1" class="risk-context-value">
                <strong>{{ displaySectionItemValue(section.items[0].name, section) }}</strong>
                <span>{{ section.items[0].value }}条</span>
              </div>
              <AnalyticsChart v-else :section="section" :compact="true" :selectable="false" />
            </article>
          </div>
        </section>
      </template>
      <section v-if="orderedVisibleSections.length && !isHospitalSelectionActive" class="section-grid" :class="{ 'cohort-section-grid': config.layout === 'cohort', 'risk-section-grid': config.layout === 'risk', 'payment-section-grid': config.layout === 'payments', 'stage-section-grid': isStage, 'hospital-section-grid': config.endpoint === '/hospitals' }">
         <article v-for="section in orderedVisibleSections" :key="section.key" class="content-card" :class="{ 'section-card-disposition': section.key === 'disposition', 'costs-full-width-section': config.layout === 'costs' && section.key === 'cost_los_relation', 'hospital-relation-section': config.endpoint === '/hospitals' && section.key === 'facility_relation', 'risk-distribution-panel': isInlineRiskDistribution(section), 'inline-risk-distribution-card': isInlineRiskDistribution(section) }">
          <template v-if="isInlineRiskDistribution(section)">
            <div class="risk-panel-heading">
              <div>
                <span class="risk-panel-kicker">{{ distributionKicker(section) }}</span>
                <h2>{{ distributionTitle(section) }}</h2>
              </div>
              <span>按等级</span>
            </div>
            <RiskDistributionChart :section="distributionSection(section)" :selectable="false" />
          </template>
          <template v-else>
            <h2>{{ displayText(section.title) }}</h2>
            <template v-if="section.items?.length || ['grouped_bar', 'scatter', 'heatmap', 'correlation'].includes(section.type)">
              <RankingVisual v-if="isDiseaseRankingVisual(section)" :section="section" :selectable="false" />
              <AnalyticsChart v-else :section="section" :selectable="false" />
            </template>
            <p v-else class="section-empty">当前条件没有可展示的条目。</p>
          </template>
        </article>
      </section>
       <footer class="data-footer">
         <span>按住院出院记录计数，不等同于患者人数</span>
       </footer>
    </template>
  </div>
</template>
