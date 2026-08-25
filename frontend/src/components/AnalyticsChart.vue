<script setup>
import { init, use } from 'echarts/core'
import { BarChart, HeatmapChart, PieChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import VisualizationTable from './VisualizationTable.vue'

// Explicit imports keep the ECharts bundle limited to the renderer families
// accepted by the snapshot contract. No server-provided option is evaluated.
use([BarChart, HeatmapChart, PieChart, ScatterChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const props = defineProps({ section: { type: Object, required: true } })
const emit = defineEmits(['select'])
const chartTypes = new Set(['bar', 'pie', 'grouped_bar', 'scatter', 'heatmap'])
const listTypes = new Set(['status'])
const element = ref(null)
let chart
let observer
let resizeFrame = 0
let chartCounter = 0
const summaryId = `chart-summary-${++chartCounter}`

const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
const compactNumber = new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 })
const summaryText = computed(() => props.section.visual?.summary?.text || (props.section.items?.length
  ? `本图按接口顺序展示 ${props.section.items.length} 项汇总结果；详细数值见下方数据表。`
  : '当前条件暂无可展示的汇总结果。'))

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function motionOptions() {
  return { animation: !prefersReducedMotion(), animationDuration: prefersReducedMotion() ? 0 : 200 }
}

function format(value, unit) {
  if (value == null) return '—'
  if (typeof value !== 'number') return value
  if (unit === '%') return `${numberFormat.format(value * 100)}%`
  return numberFormat.format(value)
}
function sectionUnit() {
  if (props.section.visual?.unit || props.section.unit) return props.section.visual?.unit || props.section.unit
  const context = `${props.section.key || ''} ${props.section.title || ''}`
  if (/(收费|成本|金额|费用)/.test(context)) return '美元'
  if (/(住院时长|天数)/.test(context)) return '天'
  if (/(比例|率)/.test(context)) return '%'
  if (props.section.type !== 'status') return '条'
  return ''
}
function compactFormat(value, unit) { return typeof value === 'number' && unit !== '%' ? compactNumber.format(value) : format(value, unit) }
function isChartType(type) { return chartTypes.has(type) }
function isListType(type) { return listTypes.has(type) }
function colors(index) { return ['#1E40AF', '#3B82F6', '#D97706', '#15803D', '#7C3AED'][index % 5] }
function groupLabel(value) { return value == null ? '' : (typeof value === 'number' ? numberFormat.format(value) : value) }
function commonGrid() { return { left: 28, right: 32, top: 28, bottom: 42, containLabel: true } }

function simpleBarOption(items) {
  return {
    ...motionOptions(),
    grid: { ...commonGrid(), left: 18, bottom: 22 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: params => { const point = Array.isArray(params) ? params[0] : params; return point ? `${point.name}<br/>${format(point.value, sectionUnit())}` : '' } },
    xAxis: { type: 'value', name: sectionUnit(), axisLabel: { formatter: value => compactFormat(value, sectionUnit()) }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    yAxis: { type: 'category', inverse: true, data: items.map(item => item.name), axisLabel: { width: 170, overflow: 'truncate' } },
    series: [{ type: 'bar', data: items.map(item => item.value), barMaxWidth: 22, itemStyle: { color: colors(0), borderRadius: [0, 5, 5, 0] } }],
  }
}

function groupedBarOption(items) {
  const legends = props.section.visual?.legend || []
  const keys = legends.length ? legends : [...new Map(items.flatMap(item => item.series).map(series => [series.key, { key: series.key, label: series.label }])).values()]
  return {
    ...motionOptions(),
    grid: commonGrid(),
    legend: { data: keys.map(item => item.label), top: 0, type: 'scroll' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: value => format(value, sectionUnit()) },
    xAxis: { type: 'category', data: items.map(item => item.category), axisLabel: { interval: 0, overflow: 'truncate' } },
    yAxis: { type: 'value', name: sectionUnit(), axisLabel: { formatter: value => compactFormat(value, sectionUnit()) }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    series: keys.map((key, index) => ({ name: key.label, type: 'bar', barMaxWidth: 28, itemStyle: { color: colors(index), borderRadius: [5, 5, 0, 0] }, data: items.map(item => item.series.find(series => series.key === key.key)?.value ?? null) })),
  }
}

function scatterOption(items) {
  const hasGroups = items.some(item => item.group != null)
  const groups = hasGroups
    ? [...new Map(items.map(item => [String(item.group), item.group])).values()]
    : [null]
  const sizes = items
    .map(item => item.size)
    .filter(value => typeof value === 'number' && Number.isFinite(value) && value > 0)
  const hasSizes = sizes.length > 0
  const maxSize = Math.max(...sizes, 1)
  const shapes = ['circle', 'diamond', 'triangle', 'rect', 'pin']
  return {
    ...motionOptions(),
    grid: commonGrid(),
    legend: hasGroups ? { data: groups.map(groupLabel), top: 0, type: 'scroll' } : { show: false },
    tooltip: { trigger: 'item', formatter: params => { const item = params.data.itemData; if (!item) return ''; return [`<strong>${item.name}</strong>`, `${props.section.visual?.x_label || 'X'}：${format(item.x, '天')}`, `${props.section.visual?.y_label || 'Y'}：${format(item.y, sectionUnit())}`, item.size == null ? '' : `记录数：${format(item.size, '条')}`, item.cost == null ? '' : `平均成本：${format(item.cost, '美元')}`, item.high_cost_rate == null ? '' : `高费用率：${format(item.high_cost_rate, '%')}`, item.group == null ? '' : `分组：${groupLabel(item.group)}`].filter(Boolean).join('<br/>') } },
    xAxis: { type: 'value', name: props.section.visual?.x_label || '', axisLabel: { formatter: value => format(value, '天') }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    yAxis: { type: 'value', name: props.section.visual?.y_label || sectionUnit(), axisLabel: { formatter: value => compactFormat(value, sectionUnit()) }, splitLine: { lineStyle: { color: '#e8eef5', type: 'dashed' } } },
    series: groups.map((group, groupIndex) => ({ name: groupLabel(group), type: 'scatter', symbol: shapes[groupIndex % shapes.length], itemStyle: { color: colors(groupIndex), opacity: 0.86 }, symbolSize: value => { if (!hasSizes) return 14; const size = value?.[2]; return typeof size === 'number' && size > 0 ? Math.max(10, Math.min(34, 8 + Math.sqrt(size / maxSize) * 28)) : 14 }, data: items.filter(item => (hasGroups ? String(item.group) === String(group) : true)).map(item => ({ value: item.size == null ? [item.x, item.y] : [item.x, item.y, item.size], itemData: item })) })),
  }
}

function heatmapOption(items) {
  const xLabels = [...new Set(items.map(item => item.x_label))]
  const yLabels = [...new Set(items.map(item => item.y_label))]
  const maxValue = Math.max(...items.map(item => item.value), 1)
  return {
    ...motionOptions(),
    grid: { ...commonGrid(), left: 78, bottom: 64 },
    tooltip: { position: 'top', formatter: params => { const item = params.data.itemData; if (!item) return ''; return [`<strong>${item.x_label} × ${item.y_label}</strong>`, `记录数：${format(item.value, item.unit)}`, item.numerator == null ? '' : `分子：${format(item.numerator, '条')}`, item.denominator == null ? '' : `分母：${format(item.denominator, '条')}`, item.high_risk_rate == null ? '' : `Major/Extreme 比例：${format(item.high_risk_rate, '%')}`].filter(Boolean).join('<br/>') } },
    xAxis: { type: 'category', data: xLabels, splitArea: { show: true }, axisLabel: { interval: 0, rotate: xLabels.length > 4 ? 24 : 0 } },
    yAxis: { type: 'category', data: yLabels, splitArea: { show: true } },
    visualMap: { min: 0, max: maxValue, calculable: false, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#edf7f5', '#62aaa2', '#1b6268'] }, text: ['高', '低'] },
    series: [{ type: 'heatmap', data: items.map(item => ({ value: [xLabels.indexOf(item.x_label), yLabels.indexOf(item.y_label), item.value], itemData: item })), label: { show: true, formatter: params => format(params.value?.[2], sectionUnit()) }, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: '#21494d' } } }],
  }
}

function option() {
  const items = props.section.items || []
  if (!isChartType(props.section.type) || !items.length) return null
  if (props.section.type === 'pie') return { ...motionOptions(), tooltip: { trigger: 'item', valueFormatter: value => format(value, sectionUnit()) }, legend: { bottom: 0, type: 'scroll' }, series: [{ type: 'pie', radius: ['42%', '70%'], data: items.map(item => ({ name: item.name, value: item.value })), label: { formatter: params => `${params.name} ${format(params.value, sectionUnit())}` } }] }
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
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(scheduleResize)
    observer.observe(element.value)
  }
}

watch(() => props.section, render, { deep: true })
onMounted(render)
onBeforeUnmount(() => { observer?.disconnect(); cancelScheduledResize(); chart?.dispose() })
</script>

<template>
  <dl v-if="listTypes.has(section.type)" class="status-grid" :aria-label="section.title">
    <div v-for="item in section.items" :key="item.name"><dt>{{ item.name }}</dt><dd>{{ format(item.value) }}</dd></div>
  </dl>
  <div v-else-if="section.type === 'table'" class="analytics-visualization table-visualization">
    <p v-if="section.items?.length" :id="summaryId" class="visual-summary">{{ summaryText }}</p>
    <VisualizationTable v-if="section.items?.length" :section="section" />
    <div v-else class="visual-empty" role="status"><strong>当前条件暂无表格数据</strong><span>请调整或清空已发布筛选。</span></div>
  </div>
  <div v-else-if="isChartType(section.type)" class="analytics-visualization">
    <div v-if="section.visual?.question" class="visual-question">{{ section.visual.question }}</div>
    <p :id="summaryId" class="visual-summary">{{ summaryText }}</p>
    <p class="visual-keyboard-note">图表下方提供可键盘读取的数据表，关键数值不依赖悬停或颜色。</p>
    <div v-if="section.items?.length" ref="element" class="chart-canvas" aria-hidden="true"></div>
    <div v-if="!section.items?.length" class="visual-empty" role="status"><strong>{{ section.visual?.empty?.title || '当前条件暂无关系数据' }}</strong><span>{{ section.visual?.empty?.text || '请调整或清空已发布筛选。' }}</span></div>
    <p v-if="section.visual?.summary?.related_not_causal" class="related-note">相关不等于因果；图表仅展示后端返回的聚合记录。</p>
    <VisualizationTable v-if="section.items?.length" :section="section" />
  </div>
  <div v-else class="state-panel"><span class="state-symbol">!</span><h2>暂不支持该图表类型</h2><p>该 section 未在前端白名单中登记。</p></div>
</template>
