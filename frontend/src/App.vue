<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { use, init } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { top10MockData } from './data/top10Mock.js'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const displayState = ref('success')
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

// 原型阶段直接使用固定顺序的本地数据；后续联调时只需替换数据获取/适配部分。
const chartData = top10MockData
const dataMeta = chartData[0]
let chartInstance = null
let resizeObserver = null
let reloadTimer = null

function formatNumber(value) {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function truncateText(value, maxLength) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value
}

function getAxisLabel(value, compact) {
  const item = chartData.find((dataItem) => dataItem.diagnosis_name === value)
  if (!item) return value

  return `${item.rank}. ${truncateText(item.diagnosis_name, compact ? 10 : 17)}`
}

function buildChartOption(width) {
  const compact = width < 760

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
      textStyle: {
        color: '#ffffff',
        fontSize: 13,
      },
      formatter(params) {
        const point = Array.isArray(params) ? params[0] : params
        const item = chartData[point.dataIndex]
        if (!item) return ''

        return [
          `<strong>${item.rank}. ${item.diagnosis_name}</strong>`,
          `病例量：${formatNumber(item.case_count)} ${item.unit}`,
        ].join('<br />')
      },
    },
    xAxis: {
      type: 'value',
      min: 0,
      axisLine: { lineStyle: { color: '#d7deea' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#7b879c',
        fontSize: 11,
        formatter: (value) => formatNumber(value),
      },
      splitLine: {
        lineStyle: {
          color: '#e9edf4',
          type: 'dashed',
        },
      },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: chartData.map((item) => item.diagnosis_name),
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
    series: [
      {
        type: 'bar',
        data: chartData.map((item) => item.case_count),
        barMaxWidth: 22,
        itemStyle: {
          color: '#3978d4',
          borderRadius: [0, 5, 5, 0],
        },
        label: {
          show: true,
          position: 'right',
          distance: 8,
          color: '#344054',
          fontSize: compact ? 10 : 12,
          formatter: (params) => `${formatNumber(params.value)} ${chartData[params.dataIndex].unit}`,
        },
        emphasis: {
          itemStyle: {
            color: '#245da9',
          },
        },
      },
    ],
  }
}

function renderChart() {
  if (displayState.value !== 'success' || !chartElement.value) return

  chartInstance = init(chartElement.value)
  chartInstance.setOption(buildChartOption(chartElement.value.clientWidth))

  resizeObserver = new ResizeObserver(() => {
    if (!chartInstance || !chartElement.value) return

    chartInstance.resize()
    chartInstance.setOption(buildChartOption(chartElement.value.clientWidth))
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

function setDisplayState(state) {
  clearReloadTimer()
  displayState.value = state
}

function reloadData() {
  clearReloadTimer()
  displayState.value = 'loading'
  reloadTimer = window.setTimeout(() => {
    displayState.value = 'success'
    reloadTimer = null
  }, 650)
}

watch(
  displayState,
  async (state) => {
    if (state !== 'success') {
      disposeChart()
      return
    }

    await nextTick()
    renderChart()
  },
  { flush: 'post' },
)

onMounted(async () => {
  await nextTick()
  renderChart()
})

onBeforeUnmount(() => {
  clearReloadTimer()
  disposeChart()
})
</script>

<template>
  <main class="page-shell">
    <div class="page-container">
      <header class="page-header">
        <p class="eyebrow">疾病数据原型 · ISSUE #11</p>
        <h1>疾病病例量 TOP10</h1>
        <p class="page-description">
          按主诊断查看有效住院出院记录的病例量排名，当前页面使用固定示例数据进行原型展示。
        </p>
      </header>

      <section class="prototype-toolbar" aria-label="原型状态切换">
        <div>
          <p class="toolbar-label">页面状态</p>
          <p class="toolbar-hint">用于联调前的加载、空数据和错误状态测试</p>
        </div>
        <div class="state-switcher" role="group" aria-label="选择页面状态">
          <button
            v-for="option in stateOptions"
            :key="option.value"
            type="button"
            :class="{ active: displayState === option.value }"
            :aria-pressed="displayState === option.value"
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
          <p>正在准备疾病病例量数据，请稍候。</p>
        </div>

        <div v-else-if="displayState === 'empty'" class="state-panel" role="status">
          <div class="state-icon empty-icon" aria-hidden="true">—</div>
          <h3>暂无可展示数据</h3>
          <p>当前没有符合条件的病例量记录。</p>
        </div>

        <div v-else-if="displayState === 'error'" class="state-panel" role="alert">
          <div class="state-icon error-icon" aria-hidden="true">!</div>
          <h3>数据加载失败，请稍后重试</h3>
          <p>本次请求未能完成，页面不会展示旧的统计结果。</p>
          <button class="reload-button" type="button" @click="reloadData">重新加载</button>
        </div>

        <div v-else class="chart-content">
          <div
            ref="chartElement"
            class="chart"
            role="img"
            aria-label="疾病病例量 TOP10 横向柱状图"
          ></div>
          <div class="data-meta">
            <span>数据版本：{{ dataMeta.data_version }}</span>
            <span>生成时间：{{ dataMeta.generated_at }}</span>
          </div>
          <p class="data-note">
            注：病例量表示有效住院出院记录数量，不表示患者人数。固定示例数据仅用于页面原型和状态测试。
          </p>
        </div>
      </section>
    </div>
  </main>
</template>
