<script setup>
import { reactive, ref, watch } from 'vue'
import { apiRequest, withQuery } from '../api/client.js'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const props = defineProps({ config: { type: Object, required: true } })
const state = ref('loading'), data = ref(null), error = ref(null)
const filters = reactive({}), optionSets = reactive({})
let requestId = 0

function normalizeOptions(values = []) { return values.map(item => typeof item === 'object' ? item : ({ value: item, label: item })) }
async function loadRemoteOptions() {
  for (const filter of props.config.filters || []) {
    if (!filter.remote) continue
    const remote = await apiRequest(filter.remote)
    optionSets[filter.key] = normalizeOptions(remote.options?.[filter.option])
  }
}
function setLocalOptions(payload) {
  for (const filter of props.config.filters || []) {
    const values = filter.values || payload.options?.[filter.option]
    if (!filter.remote && values) optionSets[filter.key] = normalizeOptions(values)
  }
}
async function load() {
  const current = ++requestId
  state.value = 'loading'
  data.value = null
  error.value = null
  try {
    await loadRemoteOptions()
    let path = props.config.endpoint
    if (props.config.profile && filters[props.config.profile.key]) path = `${props.config.profile.path}${encodeURIComponent(filters[props.config.profile.key])}`
    else path = withQuery(path, filters)
    const payload = await apiRequest(path)
    if (current !== requestId) return
    data.value = payload
    setLocalOptions(payload)
    const hasContent = Boolean(payload.metrics?.length || payload.sections?.some(section => section.items?.length))
    state.value = hasContent ? 'success' : 'empty'
  } catch (caught) { if (current === requestId) { error.value = caught; state.value = 'error' } }
}
function updateFilter(key, value) {
  filters[key] = value
  if (props.config.mutuallyExclusive?.includes(key) && value) {
    for (const other of props.config.mutuallyExclusive) if (other !== key) filters[other] = ''
  }
}
let debounce
watch(filters, () => { clearTimeout(debounce); debounce = setTimeout(load, 180) }, { deep: true })
watch(() => props.config, () => {
  clearTimeout(debounce)
  for (const key of Object.keys(filters)) delete filters[key]
  for (const key of Object.keys(optionSets)) delete optionSets[key]
  data.value = null
  load()
}, { immediate: true })
</script>
<template>
  <div class="page-wrap">
    <header class="page-heading">
      <div><p class="eyebrow">{{ config.eyebrow }}</p><h1>{{ data?.title || '医数云策分析模块' }}</h1><p>{{ data?.description || '正在读取统一分析快照。' }}</p></div>
      <span v-if="data?.data_version" class="version-pill">批次 {{ data.data_version }}</span>
    </header>
    <section v-if="config.filters?.length" class="filter-bar">
      <label v-for="filter in config.filters" :key="filter.key">{{ filter.label }}
        <select :value="filters[filter.key] || ''" @change="updateFilter(filter.key, $event.target.value)">
          <option value="">全部</option><option v-for="item in optionSets[filter.key]" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
    </section>
    <p v-if="data?.data_version?.startsWith('fixture:')" class="warning-note">当前显示固定联调快照，只用于并行开发与四态验收，不代表真实全量分析结论。</p>
    <PageState v-if="state !== 'success'" :state="state" :error="error" @retry="load" />
    <template v-else>
      <p v-if="config.disclaimer" class="warning-note">{{ config.disclaimer }}</p>
      <section class="metric-grid"><MetricCard v-for="item in data.metrics" :key="item.key" :metric="item" /></section>
      <section v-if="data.comparison?.length" class="comparison-grid">
        <article v-for="profile in data.comparison" :key="profile.title" class="content-card"><h2>{{ profile.title }}</h2><div class="compact-metrics"><MetricCard v-for="item in profile.metrics" :key="item.key" :metric="item" /></div></article>
      </section>
      <section class="section-grid"><article v-for="section in data.sections" :key="section.key" class="content-card"><h2>{{ section.title }}</h2><AnalyticsChart :section="section" /></article></section>
      <footer class="data-footer"><span>数据版本：{{ data.data_version }}</span><span>生成时间：{{ data.generated_at }}</span><span>记录统计不等同于患者人数</span></footer>
    </template>
  </div>
</template>
