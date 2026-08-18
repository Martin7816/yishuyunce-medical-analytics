<script setup>
import { init, use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
const props = defineProps({ section: { type: Object, required: true } })
const element = ref(null)
let chart
let observer
const format = (value) => typeof value === 'number' ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value) : value

function option() {
  const items = props.section.items || []
  if (props.section.type === 'status' || props.section.type === 'table') return null
  if (props.section.type === 'pie') return { tooltip: { trigger: 'item' }, legend: { bottom: 0 }, series: [{ type: 'pie', radius: ['42%', '70%'], data: items }] }
  return {
    animationDuration: 350, grid: { left: 18, right: 34, top: 14, bottom: 22, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: format },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    yAxis: { type: 'category', inverse: true, data: items.map(item => item.name), axisLabel: { width: 135, overflow: 'truncate' } },
    series: [{ type: 'bar', data: items.map(item => item.value), barMaxWidth: 20, itemStyle: { color: '#297b7f', borderRadius: [0, 5, 5, 0] } }],
  }
}
async function render() {
  await nextTick()
  observer?.disconnect(); chart?.dispose()
  if (!element.value || !option()) return
  chart = init(element.value); chart.setOption(option())
  observer = new ResizeObserver(() => chart?.resize()); observer.observe(element.value)
}
watch(() => props.section, render, { deep: true })
onMounted(render)
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>
<template>
  <div v-if="section.type === 'status' || section.type === 'table'" class="status-grid">
    <div v-for="item in section.items" :key="item.name"><span>{{ item.name }}</span><strong>{{ item.value }}</strong></div>
  </div>
  <div v-else ref="element" class="chart-canvas" role="img" :aria-label="section.title"></div>
</template>
