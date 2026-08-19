<script setup>
import { init, use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
const props = defineProps({ section: { type: Object, required: true } })
const chartTypes = new Set(['bar', 'pie'])
const listTypes = new Set(['status', 'table'])
const element = ref(null)
let chart
let observer
let resizeFrame = 0
const format = (value) => typeof value === 'number' ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value) : value
const compactFormat = (value) => typeof value === 'number'
  ? new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
  : value
const isChartType = (type) => chartTypes.has(type)
const isListType = (type) => listTypes.has(type)

function cancelScheduledResize() {
  if (!resizeFrame) return
  cancelAnimationFrame(resizeFrame)
  resizeFrame = 0
}

function scheduleResize() {
  cancelScheduledResize()
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = 0
    chart?.resize()
  })
}

function option() {
  const items = props.section.items || []
  if (!isChartType(props.section.type)) return null
  if (props.section.type === 'pie') return { tooltip: { trigger: 'item' }, legend: { bottom: 0 }, series: [{ type: 'pie', radius: ['42%', '70%'], data: items }] }
  return {
    animationDuration: 350, grid: { left: 18, right: 34, top: 14, bottom: 22, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const point = Array.isArray(params) ? params[0] : params
        if (!point) return ''
        return `${point.name}<br/>${format(point.value)}`
      },
    },
    xAxis: { type: 'value', axisLabel: { formatter: compactFormat }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    yAxis: { type: 'category', inverse: true, data: items.map(item => item.name), axisLabel: { width: 150, overflow: 'truncate' } },
    series: [{ type: 'bar', data: items.map(item => item.value), barMaxWidth: 20, itemStyle: { color: '#297b7f', borderRadius: [0, 5, 5, 0] } }],
  }
}
async function render() {
  await nextTick()
  observer?.disconnect(); cancelScheduledResize(); chart?.dispose()
  if (!element.value || !option()) return
  chart = init(element.value); chart.setOption(option())
  observer = new ResizeObserver(scheduleResize); observer.observe(element.value)
}
watch(() => props.section, render, { deep: true })
onMounted(render)
onBeforeUnmount(() => { observer?.disconnect(); cancelScheduledResize(); chart?.dispose() })
</script>
<template>
  <div v-if="isListType(section.type)" class="status-grid">
    <div v-for="item in section.items" :key="item.name"><span>{{ item.name }}</span><strong>{{ item.value }}</strong></div>
  </div>
  <div v-else-if="isChartType(section.type)" ref="element" class="chart-canvas" role="img" :aria-label="section.title"></div>
  <div v-else class="state-panel"><span class="state-symbol">!</span><h2>暂不支持该图表类型</h2><p>已忽略未在页面契约中登记的 section。</p></div>
</template>
