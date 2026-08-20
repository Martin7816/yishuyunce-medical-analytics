<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { apiRequest, isAbortError, withQuery } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const props = defineProps({ config: { type: Object, required: true } })

const state = ref('loading')
const data = ref(null)
const error = ref(null)
const validationMessage = ref('')
const filters = reactive({})
const optionSets = reactive({})

let requestId = 0
let activeController = null
let debounceTimer
let suppressFilterWatch = false
const remoteOptionsCache = new Map()

const hasActiveFilter = computed(() => Object.values(filters).some(value => value !== '' && value != null))
const displayedDataVersion = computed(() => data.value?.filters?.data_version || data.value?.data_version || '')

function normalizeOptions(values = []) {
  return values
    .filter(value => value != null)
    .map(item => typeof item === 'object' ? item : ({ value: item, label: item }))
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
    if (filter.valuesFrom === 'data_version' && (payload?.data_version || payload?.filters?.data_version)) {
      values = [payload.filters?.data_version || payload.data_version]
    }
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
    for (const filter of remoteFilters) {
      optionSets[filter.key] = normalizeOptions(payload?.options?.[filter.option])
    }
  }))
}

function hasContent(payload) {
  return Boolean(
    payload?.metrics?.length
      || payload?.sections?.some(section => section.items?.length),
  )
}

async function load() {
  const invalidSelection = duplicateSelectionMessage()
  if (invalidSelection) {
    clearActiveRequest()
    data.value = null
    error.value = null
    validationMessage.value = invalidSelection
    state.value = 'validation'
    return
  }

  validationMessage.value = ''
  const current = ++requestId
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  state.value = 'loading'
  data.value = null
  error.value = null

  try {
    await loadRemoteOptions(current, controller.signal)
    if (current !== requestId) return

    let path = props.config.endpoint
    if (props.config.profile && filters[props.config.profile.key]) {
      path = `${props.config.profile.path}${encodeURIComponent(filters[props.config.profile.key])}`
    } else {
      path = withQuery(path, filters)
    }

    const payload = await apiRequest(path, { signal: controller.signal })
    if (current !== requestId) return
    data.value = payload
    setLocalOptions(payload)
    state.value = hasContent(payload) ? 'success' : 'empty'
  } catch (caught) {
    if (current !== requestId || controller.signal.aborted || isAbortError(caught)) return
    error.value = caught
    state.value = 'error'
  } finally {
    if (current === requestId && activeController === controller) activeController = null
  }
}

function scheduleLoad() {
  clearTimeout(debounceTimer)
  const invalidSelection = duplicateSelectionMessage()
  if (invalidSelection) {
    clearActiveRequest()
    data.value = null
    error.value = null
    validationMessage.value = invalidSelection
    state.value = 'validation'
    return
  }
  validationMessage.value = ''
  debounceTimer = setTimeout(load, 180)
}

function updateFilter(key, value) {
  filters[key] = value
  if (props.config.mutuallyExclusive?.includes(key) && value) {
    for (const other of props.config.mutuallyExclusive) {
      if (other !== key) filters[other] = ''
    }
  }
  scheduleLoad()
}

function isFilterDisabled(filter) {
  const mutuallyExclusive = props.config.mutuallyExclusive || []
  if (!mutuallyExclusive.includes(filter.key)) return false
  return mutuallyExclusive.some(key => key !== filter.key && filters[key])
}

function clearFilters() {
  for (const filter of props.config.filters || []) filters[filter.key] = ''
  scheduleLoad()
}

watch(filters, () => {
  if (!suppressFilterWatch) scheduleLoad()
}, { deep: true })

watch(() => props.config, () => {
  clearTimeout(debounceTimer)
  clearActiveRequest()
  remoteOptionsCache.clear()
  suppressFilterWatch = true
  for (const key of Object.keys(filters)) delete filters[key]
  for (const key of Object.keys(optionSets)) delete optionSets[key]
  for (const filter of props.config.filters || []) filters[filter.key] = ''
  suppressFilterWatch = false
  data.value = null
  error.value = null
  validationMessage.value = ''
  load()
}, { immediate: true })

onBeforeUnmount(() => {
  clearTimeout(debounceTimer)
  clearActiveRequest()
})
</script>

<template>
  <div class="page-wrap">
    <header class="page-heading">
      <div>
        <p class="eyebrow">{{ config.eyebrow }}</p>
        <h1>{{ data?.title || config.title || '医数云策分析模块' }}</h1>
        <p>{{ data?.description || '正在读取统一分析快照。' }}</p>
      </div>
      <span v-if="displayedDataVersion" class="version-pill" :title="displayedDataVersion">批次 {{ displayedDataVersion }}</span>
    </header>

    <p v-if="config.boundaryNotice" class="warning-note medical-boundary-note" role="note">{{ config.boundaryNotice }}</p>
    <section v-if="config.filters?.length" class="filter-bar" aria-label="分析筛选">
      <label v-for="filter in config.filters" :key="filter.key" :for="`filter-${filter.key}`">
        {{ filter.label }}
        <select
          :id="`filter-${filter.key}`"
          :value="filters[filter.key] || ''"
          :aria-label="filter.label"
          :disabled="isFilterDisabled(filter)"
          @change="updateFilter(filter.key, $event.target.value)"
        >
          <option value="">{{ filter.includeAll === false ? (filter.placeholder || '请选择') : '全部' }}</option>
          <option v-for="item in optionSets[filter.key]" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <button v-if="config.alwaysShowClear || hasActiveFilter || validationMessage" type="button" class="secondary-button" @click="clearFilters">清空筛选</button>
    </section>
    <p v-if="validationMessage" class="filter-notice" role="alert">{{ validationMessage }}</p>
    <p v-if="displayedDataVersion.startsWith('fixture:')" class="warning-note">当前显示固定联调快照，只用于并行开发与四态验收，不代表真实全量分析结论。</p>

    <PageState v-if="state !== 'success' && !validationMessage" :state="state" :error="error" @retry="load" />
    <template v-else-if="state === 'success'">
      <p v-if="config.disclaimer" class="warning-note">{{ config.disclaimer }}</p>
      <template v-if="data.comparison?.length">
        <section class="comparison-grid">
          <article v-for="(profile, profileIndex) in data.comparison" :key="`comparison-${profileIndex}`" class="content-card comparison-card">
            <h2>{{ profile.title }}</h2>
            <p v-if="profile.description" class="profile-description">{{ profile.description }}</p>
            <div class="compact-metrics">
              <MetricCard
                v-for="item in profile.metrics"
                :key="item.key"
                :metric="item"
                :highlighted="Boolean(config.highlightMetricKey && filters[config.highlightMetricKey] === item.key)"
              />
            </div>
            <div v-if="profile.sections?.length" class="profile-section-grid">
              <section v-for="(section, sectionIndex) in profile.sections" :key="`${profileIndex}-${section.key}-${sectionIndex}`" class="profile-section">
                <h3>{{ section.title }}</h3>
                <AnalyticsChart v-if="section.items?.length" :section="section" />
                <p v-else class="section-empty">当前条件没有可展示的条目。</p>
              </section>
            </div>
          </article>
        </section>
      </template>
      <template v-else>
        <section class="metric-grid">
          <MetricCard
            v-for="item in data.metrics"
            :key="item.key"
            :metric="item"
            :highlighted="Boolean(config.highlightMetricKeys?.includes(item.key))"
          />
        </section>
        <section
          class="section-grid"
          :class="{
            'cohort-section-grid': config.layout === 'cohort',
            'risk-section-grid': config.layout === 'risk',
            'payment-section-grid': config.layout === 'payments',
            'quality-section-grid': config.layout === 'quality',
          }"
        >
          <article v-for="section in data.sections" :key="section.key" class="content-card" :class="{ 'section-card-disposition': section.key === 'disposition', 'quality-section-card': config.layout === 'quality' }">
            <h2>{{ section.title }}</h2>
            <AnalyticsChart v-if="section.items?.length" :section="section" />
            <p v-else class="section-empty">当前条件没有可展示的条目。</p>
          </article>
        </section>
      </template>
      <footer class="data-footer"><span>数据版本：{{ displayedDataVersion }}</span><span>生成时间：{{ data.generated_at }}</span><span>记录统计不等同于患者人数</span></footer>
    </template>
  </div>
</template>
