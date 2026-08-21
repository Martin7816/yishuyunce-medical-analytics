<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiRequest, isAbortError, withQuery } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import InsightPanel from '../components/InsightPanel.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

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

let requestId = 0
let activeController = null
let debounceTimer
const remoteOptionsCache = new Map()

const isStage = computed(() => Boolean(props.config.stage && route.query.mode === 'screen'))
const hasActiveFilter = computed(() => Object.values(filters).some(value => value !== '' && value != null))
const displayedDataVersion = computed(() => data.value?.filters?.data_version || data.value?.data_version || '')
const visibleMetrics = computed(() => {
  if (!isStage.value || !props.config.stageMetricKeys?.length) return data.value?.metrics || []
  return (data.value?.metrics || []).filter(metric => props.config.stageMetricKeys.includes(metric.key))
})

function normalizeOptions(values = []) {
  return values.filter(value => value != null).map(item => typeof item === 'object' ? item : ({ value: item, label: item }))
}

function queryValue(query, key) {
  const value = query[key]
  return Array.isArray(value) ? (typeof value[0] === 'string' ? value[0] : '') : (typeof value === 'string' ? value : '')
}

function allowedQuery() {
  const query = {}
  for (const filter of props.config.filters || []) {
    const value = filters[filter.key]
    if (value !== '' && value != null) query[filter.key] = value
  }
  if (props.config.stage && route.query.mode === 'screen') query.mode = 'screen'
  return query
}

function syncFiltersFromRoute() {
  let changed = false
  const allowed = new Set((props.config.filters || []).map(filter => filter.key))
  for (const filter of props.config.filters || []) {
    const next = queryValue(route.query, filter.key)
    if (filters[filter.key] !== next) { filters[filter.key] = next; changed = true }
  }
  const cleanQuery = {}
  for (const key of Object.keys(route.query)) {
    if (allowed.has(key) || (props.config.stage && key === 'mode' && route.query.mode === 'screen')) cleanQuery[key] = queryValue(route.query, key)
  }
  const currentQuery = JSON.stringify(route.query)
  if (JSON.stringify(cleanQuery) !== currentQuery) router.replace({ query: cleanQuery })
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

async function load() {
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
  filters[key] = value
  if (props.config.mutuallyExclusive?.includes(key) && value) {
    for (const other of props.config.mutuallyExclusive) if (other !== key) filters[other] = ''
  }
  const nextQuery = allowedQuery()
  if (JSON.stringify(nextQuery) === JSON.stringify(route.query)) scheduleLoad()
  else router.push({ query: nextQuery })
}

function isFilterDisabled(filter) {
  const mutuallyExclusive = props.config.mutuallyExclusive || []
  return mutuallyExclusive.includes(filter.key) && mutuallyExclusive.some(key => key !== filter.key && filters[key])
}

function clearFilters() {
  for (const filter of props.config.filters || []) filters[filter.key] = ''
  const nextQuery = allowedQuery()
  if (JSON.stringify(nextQuery) === JSON.stringify(route.query)) scheduleLoad()
  else router.push({ query: nextQuery })
}

function optionForLink(link, rawValue) {
  const aliases = link.aliases || {}
  const aliased = aliases[rawValue] || rawValue
  if (!link.endpoint) return aliased
  const options = linkOptionSets[link.endpoint] || []
  const match = options.find(option => String(option.value) === String(aliased) || option.label === aliased || option.label === rawValue)
  return match?.value
}

function linkFor(section, item) {
  const link = props.config.links?.[section.key]
  if (!link) return null
  const raw = item[link.itemField || 'name']
  const value = optionForLink(link, raw)
  if (value == null || value === '') return null
  return { path: link.to, query: { [link.query]: value } }
}

function linkHref(section, item) {
  const target = linkFor(section, item)
  return target ? router.resolve(target).href : null
}

function drilldownItems(section) {
  const seen = new Set()
  return (section.items || []).filter(item => {
    const target = linkFor(section, item)
    if (!target) return false
    const key = JSON.stringify(target)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function navigateTo(section, item) {
  const target = linkFor(section, item)
  if (target) router.push(target)
}

function handleSectionSelect(section, item) { navigateTo(section, item) }

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
  clearTimeout(debounceTimer); clearActiveRequest(); remoteOptionsCache.clear()
  for (const key of Object.keys(filters)) delete filters[key]
  for (const key of Object.keys(optionSets)) delete optionSets[key]
  for (const key of Object.keys(linkOptionSets)) delete linkOptionSets[key]
  for (const filter of props.config.filters || []) filters[filter.key] = ''
  syncFiltersFromRoute(); data.value = null; error.value = null; validationMessage.value = ''; load()
}, { immediate: true })

watch(() => route.fullPath, () => {
  const changed = syncFiltersFromRoute()
  if (changed) load()
})

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange))
onBeforeUnmount(() => { clearTimeout(debounceTimer); clearActiveRequest(); document.removeEventListener('fullscreenchange', onFullscreenChange) })
</script>

<template>
  <div class="page-wrap" :class="{ 'screen-mode': isStage }">
    <a class="skip-link" href="#analysis-content">跳到主要内容</a>
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ config.eyebrow }}</p>
        <h1 id="analysis-content">{{ data?.title || config.title || '医数云策分析模块' }}</h1>
        <p>{{ data?.description || '正在读取统一分析快照。' }}</p>
      </div>
      <div class="heading-actions">
        <button v-if="config.stage" type="button" class="secondary-button" @click="setStage(!isStage)">{{ isStage ? '退出大屏' : '进入大屏' }}</button>
        <button v-if="isStage" type="button" class="secondary-button" @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '浏览器全屏' }}</button>
        <span v-if="displayedDataVersion" class="version-pill" :title="displayedDataVersion">批次 {{ displayedDataVersion }}</span>
      </div>
    </header>
    <p v-if="fullscreenError" class="filter-notice" role="alert">{{ fullscreenError }}</p>
    <p v-if="config.boundaryNotice" class="warning-note medical-boundary-note" role="note">{{ config.boundaryNotice }}</p>
    <section v-if="config.filters?.length" class="filter-bar" aria-label="分析筛选">
      <label v-for="filter in config.filters" :key="filter.key" :for="`filter-${filter.key}`">
        {{ filter.label }}
        <select :id="`filter-${filter.key}`" :value="filters[filter.key] || ''" :aria-label="filter.label" :disabled="isFilterDisabled(filter)" @change="updateFilter(filter.key, $event.target.value)">
          <option value="">{{ filter.includeAll === false ? (filter.placeholder || '请选择') : '全部' }}</option>
          <option v-for="item in optionSets[filter.key]" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <button v-if="config.alwaysShowClear || hasActiveFilter || validationMessage" type="button" class="secondary-button" @click="clearFilters">清空筛选</button>
    </section>
    <p v-if="validationMessage" class="filter-notice" role="alert">{{ validationMessage }}</p>
    <p v-if="displayedDataVersion.startsWith('fixture:')" class="warning-note">当前显示固定联调快照，仅用于并行开发与四态验收，不代表真实全量分析结论。</p>

    <PageState v-if="state !== 'success' && !validationMessage" :state="state" :error="error" @retry="load" />
    <template v-else-if="state === 'success'">
      <p v-if="config.disclaimer" class="warning-note">{{ config.disclaimer }}</p>
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
        <article v-for="section in data.sections" :key="section.key" class="content-card" :class="{ 'section-card-disposition': section.key === 'disposition', 'quality-section-card': config.layout === 'quality' }">
          <h2>{{ section.title }}</h2>
          <AnalyticsChart v-if="section.items?.length || ['grouped_bar', 'scatter', 'heatmap'].includes(section.type)" :section="section" @select="handleSectionSelect(section, $event)" />
          <p v-else class="section-empty">当前条件没有可展示的条目。</p>
          <nav v-if="drilldownItems(section).length" class="section-drilldown" :aria-label="`${section.title}下钻`">
            <span>下钻：</span><a v-for="item in drilldownItems(section)" :key="`${section.key}-${item.name || item.x_label}`" :href="linkHref(section, item)" @click.prevent="navigateTo(section, item)">{{ item.name || item.x_label }}</a>
          </nav>
        </article>
      </section>
      <InsightPanel :insights="data.insights" :stage="isStage" />
      <footer class="data-footer"><span>数据版本：{{ displayedDataVersion }}</span><span>生成时间：{{ data.generated_at }}</span><span>记录统计不等同于患者人数</span></footer>
    </template>
  </div>
</template>
