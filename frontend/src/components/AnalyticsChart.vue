<script setup>
import { init, use } from 'echarts/core'
import { BarChart, HeatmapChart, PieChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import VisualizationTable from './VisualizationTable.vue'

// Explicit imports keep the ECharts bundle limited to the renderer families
// accepted by the snapshot contract. No server-provided option is evaluated.
use([BarChart, HeatmapChart, PieChart, ScatterChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const props = defineProps({ section: { type: Object, required: true } })
const emit = defineEmits(['select'])
const chartTypes = new Set(['bar', 'pie', 'grouped_bar', 'scatter', 'heatmap'])
const listTypes = new Set(['status', 'table'])
const element = ref(null)
let chart
let observer
let resizeFrame = 0

const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
const compactNumber = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 })

function format(value, unit) {
  if (value == null) return '—'
  if (typeof value !== 'number') return value
  if (unit === '%') return `${numberFormat.format(value * 100)}%`
  return numberFormat.format(value)
}
function compactFormat(value, unit) { return typeof value === 'number' && unit !== '%' ? compactNumber.format(value) : format(value, unit) }
function isChartType(type) { return chartTypes.has(type) }
function isListType(type) { return listTypes.has(type) }
function colors(index) { return ['#24777b', '#ce8b4a', '#5f7eb5', '#9b628e', '#6d9968'][index % 5] }
function groupLabel(value) { return typeof value === 'number' ? numberFormat.format(value) : value }
function commonGrid() { return { left: 28, right: 32, top: 28, bottom: 42, containLabel: true } }

function simpleBarOption(items) {
  return {
    animationDuration: 250,
    grid: { ...commonGrid(), left: 18, bottom: 22 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: params => { const point = Array.isArray(params) ? params[0] : params; return point ? `${point.name}<br/>${format(point.value, props.section.visual?.unit)}` : '' } },
    xAxis: { type: 'value', axisLabel: { formatter: value => compactFormat(value, props.section.visual?.unit) }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    yAxis: { type: 'category', inverse: true, data: items.map(item => item.name), axisLabel: { width: 170, overflow: 'truncate' } },
    series: [{ type: 'bar', data: items.map(item => item.value), barMaxWidth: 22, itemStyle: { color: colors(0), borderRadius: [0, 5, 5, 0] } }],
  }
}

function groupedBarOption(items) {
  const legends = props.section.visual?.legend || []
  const keys = legends.length ? legends : [...new Map(items.flatMap(item => item.series).map(series => [series.key, { key: series.key, label: series.label }])).values()]
  return {
    animationDuration: 250,
    grid: commonGrid(),
    legend: { data: keys.map(item => item.label), top: 0, type: 'scroll' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: value => format(value, props.section.visual?.unit) },
    xAxis: { type: 'category', data: items.map(item => item.category), axisLabel: { interval: 0, overflow: 'truncate' } },
    yAxis: { type: 'value', name: props.section.visual?.unit || '', axisLabel: { formatter: value => compactFormat(value, props.section.visual?.unit) }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    series: keys.map((key, index) => ({ name: key.label, type: 'bar', barMaxWidth: 28, itemStyle: { color: colors(index), borderRadius: [5, 5, 0, 0] }, data: items.map(item => item.series.find(series => series.key === key.key)?.value ?? null) })),
  }
}

function scatterOption(items) {
  const groups = [...new Map(items.map(item => [String(item.group), item.group])).values()]
  const maxSize = Math.max(...items.map(item => item.size), 1)
  const shapes = ['circle', 'diamond', 'triangle', 'rect', 'pin']
  return {
    animationDuration: 250,
    grid: commonGrid(),
    legend: { data: groups.map(groupLabel), top: 0, type: 'scroll' },
    tooltip: { trigger: 'item', formatter: params => { const item = params.data.itemData; if (!item) return ''; return [`<strong>${item.name}</strong>`, `${props.section.visual?.x_label || 'X'}：${format(item.x, '天')}`, `${props.section.visual?.y_label || 'Y'}：${format(item.y, props.section.visual?.unit)}`, `记录数：${format(item.size, '条')}`, item.cost == null ? '' : `平均成本：${format(item.cost, '美元')}`, item.high_cost_rate == null ? '' : `高费用率：${format(item.high_cost_rate, '%')}`, `分组：${groupLabel(item.group)}`].filter(Boolean).join('<br/>') } },
    xAxis: { type: 'value', name: props.section.visual?.x_label || '', axisLabel: { formatter: value => format(value, '天') }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    yAxis: { type: 'value', name: props.section.visual?.y_label || '', axisLabel: { formatter: value => compactFormat(value, props.section.visual?.unit) }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    series: groups.map((group, groupIndex) => ({ name: groupLabel(group), type: 'scatter', symbol: shapes[groupIndex % shapes.length], itemStyle: { color: colors(groupIndex), opacity: 0.86 }, symbolSize: value => Math.max(10, Math.min(34, 8 + Math.sqrt((value?.[2] || 0) / maxSize) * 28)), data: items.filter(item => String(item.group) === String(group)).map(item => ({ value: [item.x, item.y, item.size], itemData: item })) })),
  }
}

function heatmapOption(items) {
  const xLabels = [...new Set(items.map(item => item.x_label))]
  const yLabels = [...new Set(items.map(item => item.y_label))]
  const maxValue = Math.max(...items.map(item => item.value), 1)
  return {
    animationDuration: 250,
    grid: { ...commonGrid(), left: 78, bottom: 64 },
    tooltip: { position: 'top', formatter: params => { const item = params.data.itemData; if (!item) return ''; return [`<strong>${item.x_label} × ${item.y_label}</strong>`, `记录数：${format(item.value, item.unit)}`, item.numerator == null ? '' : `分子：${format(item.numerator, '条')}`, item.denominator == null ? '' : `分母：${format(item.denominator, '条')}`, item.high_risk_rate == null ? '' : `Major/Extreme 比例：${format(item.high_risk_rate, '%')}`].filter(Boolean).join('<br/>') } },
    xAxis: { type: 'category', data: xLabels, splitArea: { show: true }, axisLabel: { interval: 0, rotate: xLabels.length > 4 ? 24 : 0 } },
    yAxis: { type: 'category', data: yLabels, splitArea: { show: true } },
    visualMap: { min: 0, max: maxValue, calculable: false, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#edf7f5', '#62aaa2', '#1b6268'] }, text: ['高', '低'] },
    series: [{ type: 'heatmap', data: items.map(item => ({ value: [xLabels.indexOf(item.x_label), yLabels.indexOf(item.y_label), item.value], itemData: item })), label: { show: true, formatter: params => format(params.value?.[2], props.section.visual?.unit) }, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: '#21494d' } } }],
  }
}

function option() {
  const items = props.section.items || []
  if (!isChartType(props.section.type) || !items.length) return null
  if (props.section.type === 'pie') return { tooltip: { trigger: 'item', valueFormatter: value => format(value, props.section.visual?.unit) }, legend: { bottom: 0, type: 'scroll' }, series: [{ type: 'pie', radius: ['42%', '70%'], data: items.map(item => ({ name: item.name, value: item.value })), label: { formatter: params => `${params.name} ${format(params.value, props.section.visual?.unit)}` } }] }
  if (props.section.type === 'grouped_bar') return groupedBarOption(items)
  if (props.section.type === 'scatter') return scatterOption(items)
  if (props.section.type === 'heatmap') return heatmapOption(items)
  return simpleBarOption(items)
}

function handleChartClick(params) {
  const item = params?.data?.itemData || props.section.items?.[params?.dataIndex]
  if (item) emit('select', item)
}
function cancelScheduledResize() { if (resizeFrame) { cancelAnimationFrame(resizeFrame); resizeFrame = 0 } }
function scheduleResize() { cancelScheduledResize(); resizeFrame = requestAnimationFrame(() => { resizeFrame = 0; chart?.resize() }) }

async function render() {
  await nextTick()
  observer?.disconnect(); cancelScheduledResize(); chart?.dispose(); chart = null
  if (!element.value || !option()) return
  chart = init(element.value)
  chart.setOption({ aria: { enabled: true }, ...option() })
  chart.on('click', handleChartClick)
  observer = new ResizeObserver(scheduleResize)
  observer.observe(element.value)
}

watch(() => props.section, render, { deep: true })
onMounted(render)
onBeforeUnmount(() => { observer?.disconnect(); cancelScheduledResize(); chart?.dispose() })
</script>

<template>
  <div v-if="listTypes.has(section.type)" class="status-grid">
    <div v-for="item in section.items" :key="item.name"><span>{{ item.name }}</span><strong>{{ format(item.value) }}</strong></div>
  </div>
  <div v-else-if="isChartType(section.type)" class="analytics-visualization">
    <div v-if="section.visual?.question" class="visual-question">{{ section.visual.question }}</div>
    <div v-if="section.items?.length" ref="element" class="chart-canvas" role="img" :aria-label="section.title" tabindex="0"></div>
    <div v-if="!section.items?.length" class="visual-empty" role="status"><strong>{{ section.visual?.empty?.title || '当前条件暂无关系数据' }}</strong><span>{{ section.visual?.empty?.text || '请调整或清空已发布筛选。' }}</span></div>
    <p v-if="section.visual?.summary?.related_not_causal" class="related-note">相关不等于因果；图表仅展示后端返回的聚合记录。</p>
    <VisualizationTable v-if="section.items?.length" :section="section" />
  </div>
  <div v-else class="state-panel"><span class="state-symbol">!</span><h2>暂不支持该图表类型</h2><p>该 section 未在前端白名单中登记。</p></div>
</template>
