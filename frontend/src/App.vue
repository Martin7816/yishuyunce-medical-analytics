<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use, init } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { DiseaseTop10ApiError, fetchDiseaseTop10 } from './api/diseaseTop10.js'
import { top10MockResponses } from './data/top10Mock.js'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const isMockMode = (import.meta.env.VITE_TOP10_MODE || '').toLowerCase() === 'mock'
const configuredMockState = (import.meta.env.VITE_TOP10_MOCK_STATE || 'success').toLowerCase()

const displayState = ref('loading')
const chartData = ref([])
const dataMeta = ref({ unit: '', data_version: '', generated_at: '' })
const errorCode = ref('')
const errorTraceId = ref('')
const mockState = ref(['loading', 'success', 'empty', 'error'].includes(configuredMockState)
  ? configuredMockState
  : 'success')
const chartElement = ref(null)

const stateOptions = [
  { value: 'loading', label: 'loading' },
  { value: 'success', label: 'success' },
  { value: 'empty', label: 'empty' },
  { value: 'error', label: 'error' },
]

const stateLabels = {
  loading: '加载中',
  success: '正常',
  empty: '空数据',
  error: '错误',
}

const errorMessages = {
  DATABASE_UNAVAILABLE: '数据服务暂时不可用，请稍后重试。',
  RESULT_NOT_READY: 'TOP10 结果尚未发布，请稍后重试。',
  SERVER_MISCONFIGURED: '数据服务配置不完整，请联系维护人员。',
  SERVICE_RESULT_INVALID: '服务结果校验失败，请联系维护人员。',
  INVALID_QUERY_PARAMETER: '请求参数不受支持。',
  INVALID_REQUEST_FORMAT: '请求格式无效。',
  METHOD_NOT_ALLOWED: '请求方法不受支持。',
  RESOURCE_NOT_FOUND: '请求的资源不存在。',
  NETWORK_ERROR: '无法连接数据服务，请确认后端已启动。',
  INTERNAL_ERROR: '数据服务发生内部错误，请稍后重试。',
}

let chartInstance = null
let resizeObserver = null
let reloadTimer = null
let requestId = 0

function formatNumber(value) {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatUnit(unit) {
  if (unit === 'discharge_records') return '有效住院出院记录'
  return unit || '有效住院出院记录'
}

function truncateText(value, maxLength) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value
}

function getAxisLabel(value, compact) {
  const item = chartData.value.find((dataItem) => dataItem.diagnosis_name === value)
  if (!item) return value
  return `${item.rank}. ${truncateText(item.diagnosis_name, compact ? 10 : 17)}`
}

function buildChartOption(width) {
  const compact = width < 760
  const unit = formatUnit(dataMeta.value.unit)
  const items = chartData.value

  return {
    animation: false,
    grid: {
      top: 16,
      right: compact ? 58 : 88,
      bottom: 34,
      left: compact ? 152 : 292,
      containLabel: false,
    },
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: '#172033',
      borderWidth: 0,
      textStyle: { color: '#ffffff', fontSize: 13 },
      formatter(params) {
        const point = Array.isArray(params) ? params[0] : params
        const item = items[point.dataIndex]
        if (!item) return ''
        return [
          `<strong>${item.rank}. ${item.diagnosis_name}</strong>`,
          `病例量：${formatNumber(item.case_count)} ${unit}`,
        ].join('<br />')
      },
    },
    xAxis: {
      type: 'value',
      min: 0,
      axisLine: { lineStyle: { color: '#d7deea' } },
      axisTick: { show: false },
      axisLabel: { color: '#7b879c', fontSize: 11, formatter: (value) => formatNumber(value) },
      splitLine: { lineStyle: { color: '#e9edf4', type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: items.map((item) => item.diagnosis_name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#344054',
        fontSize: compact ? 11 : 12,
        margin: compact ? 10 : 14,
        align: 'right',
        formatter: (value) => getAxisLabel(value, compact),
      },
    },
    series: [{
      type: 'bar',
      data: items.map((item) => item.case_count),
      barMaxWidth: 22,
      itemStyle: { color: '#3978d4', borderRadius: [0, 5, 5, 0] },
      label: {
        show: true,
        position: 'right',
        distance: 8,
        color: '#344054',
        fontSize: compact ? 10 : 12,
        formatter: (params) => `${formatNumber(params.value)} ${unit}`,
      },
      emphasis: { itemStyle: { color: '#245da9' } },
    }],
  }
}

function renderChart() {
  if (displayState.value !== 'success' || !chartElement.value) return
  chartInstance = init(chartElement.value)
  chartInstance.setOption(buildChartOption(chartElement.value.clientWidth || 600))
  resizeObserver = new ResizeObserver(() => {
    if (!chartInstance || !chartElement.value) return
    chartInstance.resize()
    chartInstance.setOption(buildChartOption(chartElement.value.clientWidth || 600))
  })
  resizeObserver.observe(chartElement.value)
}

function disposeChart() {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

function clearReloadTimer() {
  if (reloadTimer) {
    window.clearTimeout(reloadTimer)
    reloadTimer = null
  }
}

function clearResult() {
  chartData.value = []
  dataMeta.value = { unit: '', data_version: '', generated_at: '' }
  errorCode.value = ''
  errorTraceId.value = ''
}

function applySuccess(data) {
  chartData.value = data.items
  dataMeta.value = {
    unit: data.unit,
    data_version: data.data_version,
    generated_at: data.generated_at,
  }
  errorCode.value = ''
  errorTraceId.value = ''
  displayState.value = data.items.length > 0 ? 'success' : 'empty'
}

function applyError(error) {
  clearResult()
  errorCode.value = error.code || 'INTERNAL_ERROR'
  errorTraceId.value = error.traceId || ''
  displayState.value = 'error'
}

function loadMockData(state, currentRequestId) {
  if (state === 'loading') return
  reloadTimer = window.setTimeout(() => {
    if (currentRequestId !== requestId) return
    if (state === 'error') {
      applyError(new DiseaseTop10ApiError({ code: 'DATABASE_UNAVAILABLE' }))
    } else {
      applySuccess(top10MockResponses[state].data)
    }
    reloadTimer = null
  }, 450)
}

async function loadData({ mockStateOverride } = {}) {
  clearReloadTimer()
  const currentRequestId = ++requestId
  clearResult()
  displayState.value = 'loading'

  if (isMockMode) {
    const state = mockStateOverride || mockState.value
    mockState.value = state
    loadMockData(state, currentRequestId)
    return
  }

  try {
    const data = await fetchDiseaseTop10()
    if (currentRequestId !== requestId) return
    applySuccess(data)
  } catch (error) {
    if (currentRequestId !== requestId) return
    applyError(error)
  }
}

function setDisplayState(state) {
  if (!isMockMode) return
  clearReloadTimer()
  mockState.value = state
  clearResult()
  displayState.value = state
  if (state !== 'loading') loadData({ mockStateOverride: state })
}

function reloadData() {
  if (isMockMode) {
    loadData({ mockStateOverride: 'success' })
  } else {
    loadData()
  }
}

function errorMessage() {
  return errorMessages[errorCode.value] || '数据请求失败，请稍后重试。'
}

watch(displayState, async (state) => {
  if (state !== 'success') {
    disposeChart()
    return
  }
  await nextTick()
  disposeChart()
  renderChart()
}, { flush: 'post' })

onMounted(() => loadData())

onBeforeUnmount(() => {
  clearReloadTimer()
  requestId += 1
  disposeChart()
})
</script>

<template>
  <main class="page-shell">
    <div class="page-container">
      <header class="page-header">
        <p class="eyebrow">疾病数据 · ISSUE #25</p>
        <h1>疾病病例量 TOP10</h1>
        <p class="page-description">
          按主诊断查看有效住院出院记录的病例量排名。页面只渲染正式 API 返回的结果，不在浏览器重新计算、排序或截断 TOP10。
        </p>
      </header>

      <section v-if="isMockMode" class="prototype-toolbar" aria-label="Mock 状态切换">
        <div>
          <p class="toolbar-label">Mock 状态</p>
          <p class="toolbar-hint">仅用于复现页面状态；正式模式默认请求 Flask API。</p>
        </div>
        <div class="state-switcher" role="group" aria-label="选择 Mock 状态">
          <button
            v-for="option in stateOptions"
            :key="option.value"
            type="button"
            :class="{ active: mockState === option.value }"
            :aria-pressed="mockState === option.value"
            @click="setDisplayState(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </section>

      <section class="chart-card" :aria-busy="displayState === 'loading'">
        <div class="card-heading">
          <div>
            <p class="card-kicker">主诊断统计</p>
            <h2>有效住院出院记录数量</h2>
          </div>
          <span class="state-badge" :class="`state-${displayState}`">
            {{ stateLabels[displayState] }}
          </span>
        </div>

        <div v-if="displayState === 'loading'" class="state-panel" role="status">
          <div class="state-icon loading-icon" aria-hidden="true">···</div>
          <h3>数据加载中……</h3>
          <p>正在请求疾病病例量数据，请稍候。</p>
        </div>

        <div v-else-if="displayState === 'empty'" class="state-panel" role="status">
          <div class="state-icon empty-icon" aria-hidden="true">—</div>
          <h3>暂无可展示数据</h3>
          <p>接口返回了合法空结果，当前没有可展示的病例量记录。</p>
        </div>

        <div v-else-if="displayState === 'error'" class="state-panel" role="alert">
          <div class="state-icon error-icon" aria-hidden="true">!</div>
          <h3>数据加载失败，请稍后重试</h3>
          <p>{{ errorMessage() }}</p>
          <small v-if="errorCode" class="error-code">
            {{ errorCode }}<span v-if="errorTraceId"> · {{ errorTraceId }}</span>
          </small>
          <button class="reload-button" type="button" @click="reloadData">重新加载</button>
        </div>

        <div v-else class="chart-content">
          <div ref="chartElement" class="chart" role="img" aria-label="疾病病例量 TOP10 横向柱状图"></div>
          <div class="data-meta">
            <span>单位：{{ formatUnit(dataMeta.unit) }}</span>
            <span>数据版本：{{ dataMeta.data_version }}</span>
            <span>生成时间：{{ dataMeta.generated_at }}</span>
          </div>
          <p class="data-note">
            注：病例量表示有效住院出院记录数量，不表示患者人数。诊断名称过长时，坐标轴使用省略显示，悬浮提示保留完整名称。
            {{ isMockMode ? '当前为 Mock 状态，仅用于页面联调。' : '当前数据来自正式 API。' }}
          </p>
        </div>
      </section>
    </div>
  </main>
</template>
