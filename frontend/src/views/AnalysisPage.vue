<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, apiRequest, isAbortError, withQuery } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import InsightPanel from '../components/InsightPanel.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'
import { prepareFilterNavigation, queryForFilters } from '../domain/filterNavigation.js'

const props = defineProps({ config: { type: Object, required: true } })
const route = useRoute()
const router = useRouter()
const state = ref('loading')
const data = ref(null)
const error = ref(null)
const validationMessage = ref('')
const filters = reactive({})
const optionSets = reactive({})
const linkOptionSets = reactive({})
const fullscreen = ref(false)
const fullscreenError = ref('')
const routeQueryMessage = ref('')
const relatedAnalysis = ref({ status: 'idle', sectionKey: '', itemKey: '', label: '', request: null, payload: null, error: null })

let requestId = 0
let relatedRequestId = 0
let activeController = null
let relatedController = null
let debounceTimer
const remoteOptionsCache = new Map()

const stageSources = [
  { endpoint: '/hospitals', sectionKeys: ['facility_relation', 'facility_metric_comparison'] },
  { endpoint: '/costs/overview', sectionKeys: ['cost_los_relation'] },
  { endpoint: '/risks/overview', sectionKeys: ['age_severity_matrix'] },
]

const isStage = computed(() => Boolean(props.config.stage && route.query.mode === 'screen'))
const hasActiveFilter = computed(() => Object.values(filters).some(value => value !== '' && value != null))
const displayedDataVersion = computed(() => data.value?.filters?.data_version || data.value?.data_version || '')
const isFixture = computed(() => displayedDataVersion.value.startsWith('fixture:'))
const displayedGeneratedAt = computed(() => data.value?.generated_at || '')
const displayedGeneratedAtText = computed(() => {
  if (!displayedGeneratedAt.value) return ''
  const date = new Date(displayedGeneratedAt.value)
  if (Number.isNaN(date.getTime())) return displayedGeneratedAt.value
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
})
const dataStatusText = computed(() => isFixture.value ? '演示数据' : '已发布数据')
const boundaryText = computed(() => props.config.boundaryNotice || '统计对象为住院出院记录，不按患者去重；页面不连接同一人的多次住院。')
const mutuallyExclusiveMessage = computed(() => props.config.mutuallyExclusive?.length
  ? '疾病与医院筛选互斥；选择其中一项后，另一项会暂时停用。'
  : '')
const visibleMetrics = computed(() => {
  const metrics = data.value?.metrics || []
  const keys = isStage.value ? props.config.stageMetricKeys : props.config.clientMetricKeys
  const visible = keys?.length ? metrics.filter(metric => keys.includes(metric.key)) : metrics
  const labels = props.config.clientMetricLabels || {}
  return visible.map(metric => labels[metric.key] ? { ...metric, label: labels[metric.key] } : metric)
})
const visibleSections = computed(() => {
  const sections = data.value?.sections || []
  const visible = props.config.clientSectionKeys?.length
    ? sections.filter(section => props.config.clientSectionKeys.includes(section.key))
    : sections
  const titles = props.config.clientSectionTitles || {}
  return visible.map(section => titles[section.key] ? { ...section, title: titles[section.key] } : section)
})
const relatedMetrics = computed(() => relatedAnalysis.value.payload?.metrics?.slice(0, 4) || [])
const relatedSections = computed(() => relatedAnalysis.value.payload?.sections || [])
const relatedPrimarySections = computed(() => relatedSections.value.slice(0, 4))
const relatedExtraSections = computed(() => relatedSections.value.slice(4))

function normalizeOptions(values = []) {
  return values.filter(value => value != null).map(item => typeof item === 'object' ? item : ({ value: item, label: item }))
}

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
    if (values) optionSets[filter.key] = normalizeOptions(values)
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
    for (const filter of remoteFilters) optionSets[filter.key] = normalizeOptions(payload?.options?.[filter.option])
  }))

  const links = props.config.linkSources || []
  await Promise.all(links.map(async source => {
    try {
      let payload = remoteOptionsCache.get(source.endpoint)
      if (!payload) {
        payload = await apiRequest(source.endpoint, { signal })
        if (current !== requestId) return
        remoteOptionsCache.set(source.endpoint, payload)
      }
      if (current === requestId) linkOptionSets[source.endpoint] = normalizeOptions(payload?.options?.[source.option])
    } catch (caught) {
      if (!isAbortError(caught)) linkOptionSets[source.endpoint] = []
    }
  }))
}

function hasContent(payload) {
  return Boolean(payload?.metrics?.length || payload?.sections?.some(section => section.items?.length))
}

function mergeStagePayload(base, relatedPayloads) {
  const allPayloads = [base, ...relatedPayloads]
  const versions = [...new Set(allPayloads.map(payload => payload?.data_version).filter(Boolean))]
  if (versions.length > 1) {
    throw new ApiError({
      code: 'INCONSISTENT_DATA_VERSION',
      message: '关联分析接口返回了不同的数据批次。',
    }, 200)
  }

  const sections = [...(base.sections || [])]
  for (const [index, source] of stageSources.entries()) {
    const payload = relatedPayloads[index]
    for (const section of payload?.sections || []) {
      if (source.sectionKeys.includes(section.key)) sections.push(section)
    }
  }

  const insights = []
  const seenInsights = new Set()
  for (const payload of allPayloads) {
    for (const insight of payload?.insights || []) {
      const key = insight.key || `${insight.title}:${insight.summary}`
      if (!seenInsights.has(key)) {
        seenInsights.add(key)
        insights.push(insight)
      }
    }
  }
  return { ...base, sections, insights }
}

async function loadStagePayload(base, signal) {
  const relatedPayloads = await Promise.all(stageSources.map(source => apiRequest(source.endpoint, { signal })))
  return mergeStagePayload(base, relatedPayloads)
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
    let payload = await apiRequest(path, { signal: controller.signal })
    if (isStage.value) payload = await loadStagePayload(payload, controller.signal)
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

function optionForLink(link, rawValue) {
  const aliases = link.aliases || {}
  const aliased = aliases[rawValue] || rawValue
  if (!link.endpoint) return aliased
  const options = linkOptionSets[link.endpoint] || []
  const match = options.find(option => String(option.value) === String(aliased) || option.label === aliased || option.label === rawValue)
  return match?.value
}

function relatedRequestFor(section, item) {
  const link = props.config.links?.[section.key]
  if (!link) return null
  const raw = item[link.itemField || (item.name != null ? 'name' : item.x_label != null ? 'x_label' : 'category')]
  const value = optionForLink(link, raw)
  if (value == null || value === '') return null
  return {
    path: link.profilePath ? `${link.profilePath}${encodeURIComponent(value)}` : (link.requestEndpoint || props.config.endpoint),
    query: link.profilePath ? {} : { [link.query]: value },
  }
}

function selectedItemLabel(section, item) {
  return item.name || item.x_label || item.category || section.title
}

function drilldownItems(section) {
  const seen = new Set()
  return (section.items || []).filter(item => {
    const target = relatedRequestFor(section, item)
    if (!target) return false
    const key = JSON.stringify(target)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function isRelatedSelected(section, item) {
  const request = relatedRequestFor(section, item)
  return Boolean(request && relatedAnalysis.value.sectionKey === section.key && relatedAnalysis.value.itemKey === JSON.stringify(request))
}

function relatedAnalysisFor(section) {
  return relatedAnalysis.value.sectionKey === section.key && relatedAnalysis.value.status !== 'idle'
}

async function loadRelatedAnalysis(selection) {
  relatedController?.abort()
  const current = ++relatedRequestId
  const controller = new AbortController()
  relatedController = controller
  relatedAnalysis.value = { ...selection, status: 'loading', payload: null, error: null }
  try {
    const payload = await apiRequest(withQuery(selection.request.path, selection.request.query), { signal: controller.signal })
    if (current !== relatedRequestId) return
    relatedAnalysis.value = { ...relatedAnalysis.value, status: hasContent(payload) ? 'success' : 'empty', payload }
  } catch (caught) {
    if (current !== relatedRequestId || controller.signal.aborted || isAbortError(caught)) return
    relatedAnalysis.value = { ...relatedAnalysis.value, status: 'error', error: caught }
  } finally {
    if (current === relatedRequestId && relatedController === controller) relatedController = null
  }
}

function handleSectionSelect(section, item) {
  const request = relatedRequestFor(section, item)
  if (!request) return
  void loadRelatedAnalysis({
    sectionKey: section.key,
    itemKey: JSON.stringify(request),
    label: selectedItemLabel(section, item),
    request,
  })
}

function retryRelatedAnalysis() {
  if (relatedAnalysis.value.request) void loadRelatedAnalysis(relatedAnalysis.value)
}

function clearRelatedAnalysis() {
  relatedRequestId += 1
  relatedController?.abort()
  relatedController = null
  relatedAnalysis.value = { status: 'idle', sectionKey: '', itemKey: '', label: '', request: null, payload: null, error: null }
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

watch(() => props.config, () => {
  clearTimeout(debounceTimer); clearActiveRequest(); clearRelatedAnalysis(); remoteOptionsCache.clear()
  for (const key of Object.keys(filters)) delete filters[key]
  for (const key of Object.keys(optionSets)) delete optionSets[key]
  for (const key of Object.keys(linkOptionSets)) delete linkOptionSets[key]
  for (const filter of props.config.filters || []) filters[filter.key] = ''
  syncFiltersFromRoute(); data.value = null; error.value = null; validationMessage.value = ''; load()
}, { immediate: true })

watch(() => route.fullPath, () => {
  const changed = syncFiltersFromRoute()
  if (changed || routeQueryMessage.value || state.value === 'validation') load()
})

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange))
onBeforeUnmount(() => { clearTimeout(debounceTimer); clearActiveRequest(); clearRelatedAnalysis(); document.removeEventListener('fullscreenchange', onFullscreenChange) })
</script>

<template>
  <div class="page-wrap" :class="{ 'screen-mode': isStage }" :aria-busy="state === 'loading'">
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ config.eyebrow }}</p>
         <h1 id="page-title" data-page-title tabindex="-1">{{ config.clientTitle || data?.title || config.title || '医数云策分析模块' }}</h1>
         <p id="page-description">{{ config.clientDescription || data?.description || '正在读取分析数据。' }}</p>
       </div>
       <div class="heading-actions">
         <button v-if="config.stage" type="button" class="secondary-button" @click="setStage(!isStage)">{{ isStage ? '退出大屏' : '大屏演示' }}</button>
         <button v-if="isStage" type="button" class="secondary-button" @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '浏览器全屏' }}</button>
       </div>
     </header>
     <p v-if="fullscreenError" class="filter-notice" role="alert">{{ fullscreenError }}</p>
     <p class="boundary-note" role="note"><strong>统计范围</strong>{{ boundaryText }}</p>
     <fieldset v-if="config.filters?.length" class="filter-bar">
       <legend class="filter-legend">筛选条件</legend>
      <label v-for="filter in config.filters" :key="filter.key" :for="`filter-${filter.key}`">
        {{ filter.label }}
        <select :id="`filter-${filter.key}`" :value="filters[filter.key] || ''" :aria-label="filter.label" :aria-describedby="isFilterDisabled(filter) ? 'filter-help' : undefined" :disabled="isFilterDisabled(filter)" @change="updateFilter(filter.key, $event.target.value)">
          <option value="">{{ filter.includeAll === false ? (filter.placeholder || '请选择') : '全部' }}</option>
          <option v-for="item in optionSets[filter.key]" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <button v-if="config.alwaysShowClear || hasActiveFilter || validationMessage" type="button" class="secondary-button" @click="clearFilters">清空筛选</button>
      <p v-if="mutuallyExclusiveMessage" id="filter-help" class="filter-help">{{ mutuallyExclusiveMessage }}</p>
    </fieldset>
    <p v-if="validationMessage && state !== 'validation'" class="filter-notice" role="alert">{{ validationMessage }}</p>
     <p v-if="isFixture" class="warning-note" role="note">当前为演示数据，数值仅用于展示分析功能；正式业务结论请以已发布数据为准。</p>

    <PageState v-if="state !== 'success'" :state="state" :error="error" :message="validationMessage" @retry="load" @clear="clearInvalidQuery" />
    <template v-else-if="state === 'success'">
       <section class="metric-grid" :class="{ 'stage-metric-grid': isStage }">
         <MetricCard v-for="item in visibleMetrics" :key="item.key" :metric="item" :highlighted="Boolean(config.highlightMetricKeys?.includes(item.key) || config.highlightMetricKey && filters[config.highlightMetricKey] === item.key)" />
      </section>
      <template v-if="data.comparison?.length">
        <section class="comparison-grid">
          <article v-for="(profile, profileIndex) in data.comparison" :key="`comparison-${profileIndex}`" class="content-card comparison-card">
            <h2>{{ profile.title }}</h2><p v-if="profile.description" class="profile-description">{{ profile.description }}</p>
            <div class="compact-metrics"><MetricCard v-for="item in profile.metrics" :key="item.key" :metric="item" :highlighted="Boolean(config.highlightMetricKey && filters[config.highlightMetricKey] === item.key)" /></div>
            <div v-if="profile.sections?.length" class="profile-section-grid"><section v-for="(section, sectionIndex) in profile.sections" :key="`${profileIndex}-${section.key}-${sectionIndex}`" class="profile-section"><h3>{{ section.title }}</h3><AnalyticsChart :section="section" @select="handleSectionSelect(section, $event)" /></section></div>
          </article>
        </section>
      </template>
      <section class="section-grid" :class="{ 'cohort-section-grid': config.layout === 'cohort', 'risk-section-grid': config.layout === 'risk', 'payment-section-grid': config.layout === 'payments', 'quality-section-grid': config.layout === 'quality', 'stage-section-grid': isStage }">
         <article v-for="section in visibleSections" :key="section.key" class="content-card" :class="{ 'section-card-disposition': section.key === 'disposition', 'quality-section-card': config.layout === 'quality' }">
          <h2>{{ section.title }}</h2>
          <AnalyticsChart v-if="section.items?.length || ['grouped_bar', 'scatter', 'heatmap', 'correlation'].includes(section.type)" :section="section" @select="handleSectionSelect(section, $event)" />
          <p v-else class="section-empty">当前条件没有可展示的条目。</p>
          <nav v-if="drilldownItems(section).length" class="section-drilldown" :aria-label="`${section.title}关联分析`">
            <span>选择条目开展关联分析：</span><button v-for="item in drilldownItems(section)" :key="`${section.key}-${item.name || item.x_label}`" type="button" class="related-item-button" :class="{ active: isRelatedSelected(section, item) }" @click="handleSectionSelect(section, item)">{{ selectedItemLabel(section, item) }}</button>
          </nav>
          <aside v-if="relatedAnalysisFor(section)" class="related-analysis-panel" :aria-labelledby="`related-analysis-${section.key}`">
            <div class="related-analysis-heading">
              <div>
                <p class="eyebrow">数据拓展</p>
                <h3 :id="`related-analysis-${section.key}`">围绕“{{ relatedAnalysis.label }}”的关联分析</h3>
                <p>基于当前已发布数据展开相关维度，不跳转到其他业务页面。</p>
              </div>
              <button type="button" class="secondary-button" @click="clearRelatedAnalysis">收起</button>
            </div>
            <PageState v-if="relatedAnalysis.status !== 'success'" :state="relatedAnalysis.status" :error="relatedAnalysis.error" @retry="retryRelatedAnalysis" />
            <template v-else>
              <p v-if="relatedAnalysis.payload?.description" class="related-analysis-description">{{ relatedAnalysis.payload.description }}</p>
              <div v-if="relatedMetrics.length" class="related-analysis-metrics">
                <MetricCard v-for="metric in relatedMetrics" :key="`related-${metric.key}`" :metric="metric" />
              </div>
              <div class="related-analysis-grid">
                <article v-for="relatedSection in relatedPrimarySections" :key="`related-${relatedAnalysis.itemKey}-${relatedSection.key}`" class="related-analysis-section">
                  <h4>{{ relatedSection.title }}</h4>
                  <AnalyticsChart :section="relatedSection" />
                </article>
              </div>
              <details v-if="relatedExtraSections.length" class="related-analysis-more">
                <summary>查看其他关联维度（{{ relatedExtraSections.length }}项）</summary>
                <div class="related-analysis-grid">
                  <article v-for="relatedSection in relatedExtraSections" :key="`related-more-${relatedAnalysis.itemKey}-${relatedSection.key}`" class="related-analysis-section">
                    <h4>{{ relatedSection.title }}</h4>
                    <AnalyticsChart :section="relatedSection" />
                  </article>
                </div>
              </details>
            </template>
          </aside>
        </article>
      </section>
      <InsightPanel :insights="data.insights" :stage="isStage" />
       <footer class="data-footer">
         <span>按住院出院记录计数，不等同于患者人数</span>
         <span v-if="isFixture">当前为演示数据</span>
         <details v-if="displayedDataVersion" class="data-details">
           <summary>数据说明</summary>
           <div class="data-details-content">
             <span>数据状态：{{ dataStatusText }}</span>
             <span v-if="displayedGeneratedAtText">更新时间：{{ displayedGeneratedAtText }}</span>
             <span>数据批次：{{ displayedDataVersion }}</span>
           </div>
         </details>
       </footer>
    </template>
  </div>
</template>
