<script setup>
import { computed } from 'vue'
import { d3ChartTypes, resolveChartPresentation } from '../domain/chartPresentation.js'
import { displaySectionItemValue, displayText, displayValue } from '../domain/displayLabels.js'
import D3SvgChart from './D3SvgChart.vue'
import VisualizationTable from './VisualizationTable.vue'

const props = defineProps({
  section: { type: Object, required: true },
  compact: { type: Boolean, default: false },
  showQuestion: { type: Boolean, default: false },
  businessMode: { type: Boolean, default: false },
  screenMode: { type: Boolean, default: false },
  showSummary: { type: Boolean, default: false },
  selectable: { type: Boolean, default: true },
  showDetails: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])
const listTypes = new Set(['status'])
const summaryId = `chart-summary-${Math.random().toString(36).slice(2)}`
const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false })

const presentation = computed(() => resolveChartPresentation(props.section))

function format(value) {
  if (value == null) return '—'
  return typeof value === 'number' ? numberFormat.format(value) : value
}

function itemLabel(item) {
  const field = item.name != null ? 'name' : item.category != null ? 'category' : item.x_label != null ? 'x_label' : 'y_label'
  return displaySectionItemValue(item[field] || '该分组', props.section, field)
}

function sectionUnit() {
  if (props.section.visual?.unit || props.section.unit) return props.section.visual?.unit || props.section.unit
  const context = `${props.section.key || ''} ${props.section.title || ''}`
  if (/(收费|成本|金额|费用)/.test(context)) return '美元'
  if (/(住院时长|天数)/.test(context)) return '天'
  if (/(比例|率)/.test(context)) return '%'
  return props.section.type === 'status' ? '' : '条'
}
function scatterSummary(items) {
  const points = items.filter(item => typeof item.y === 'number')
  if (!points.length) return '当前没有可展示的业务结果。'
  const top = points.reduce((current, item) => item.y > current.y ? item : current, points[0])
  const group = top.group && top.group !== '总体' ? `${displayValue(top.group, 'severity')}组` : itemLabel(top)
  const xLabel = displayText(props.section.visual?.x_label || '横轴指标')
  const yLabel = displayText(props.section.visual?.y_label || '纵轴指标')
  const encoding = props.section.key === 'cost_los_overview'
    ? '颜色表示收费成本差，点大小代表记录数'
    : '颜色区分严重程度，点大小代表记录数'
  return `横轴为${xLabel}，纵轴为${yLabel}，${encoding}；${group}的平均收费最高，为${format(top.y)}${sectionUnit()}。`
}

function heatmapSummary(items) {
  const byAge = new Map()
  for (const item of items) {
    if (typeof item.numerator !== 'number' || typeof item.denominator !== 'number') continue
    const current = byAge.get(item.x_label) || { numerator: 0, denominator: 0 }
    current.numerator += item.numerator
    current.denominator += item.denominator
    byAge.set(item.x_label, current)
  }
  const groups = [...byAge.entries()].filter(([, value]) => value.denominator > 0)
  if (!groups.length) return '当前没有可展示的业务结果。'
  const [topAge, topValue] = groups.reduce((current, item) => {
    const currentRate = current[1].numerator / current[1].denominator
    const nextRate = item[1].numerator / item[1].denominator
    return nextRate > currentRate ? item : current
  }, groups[0])
  const rate = numberFormat.format((topValue.numerator / topValue.denominator) * 100)
  return `按年龄组汇总，${displayValue(topAge, 'age_group')}组的重症/极重症占比最高，约${rate}%；可结合病例量进一步分析。`
}

function businessSummary() {
  if (!props.businessMode && props.section.visual?.summary?.text) return displayText(props.section.visual.summary.text)

  if (props.businessMode && presentation.value === 'scatter') return scatterSummary(props.section.items || [])
  if (props.businessMode && presentation.value === 'heatmap') return heatmapSummary(props.section.items || [])

  const items = (props.section.items || []).filter(item => typeof item.value === 'number')
  if (!items.length) return '当前没有可展示的业务结果。'

  const top = items.reduce((current, item) => item.value > current.value ? item : current, items[0])
  if (presentation.value === 'pie') {
    const total = items.reduce((sum, item) => sum + item.value, 0)
    const share = total > 0 ? numberFormat.format((top.value / total) * 100) : null
    return share == null
      ? `${displayText(props.section.title || '当前结构')}已按分组汇总，详细数值见下方数据表。`
      : `${displayText(props.section.title || '当前结构')}中，${itemLabel(top)}占比最高，约${share}%。`
  }

  if (props.section.visual?.summary?.text) return displayText(props.section.visual.summary.text)

  const unit = sectionUnit()
  const valueLabel = unit === '条' ? '病例量' : '数值'
  return `${displayText(props.section.title || '当前分析')}中，${itemLabel(top)}${valueLabel}最多，共${format(top.value)}${unit}。`
}

const summaryText = computed(businessSummary)

function isChartType(type) { return d3ChartTypes.has(type) }
</script>

<template>
  <dl v-if="listTypes.has(section.type)" class="status-grid" :aria-label="displayText(section.title)">
    <div v-for="item in section.items" :key="item.name"><dt>{{ displaySectionItemValue(item.name, section) }}</dt><dd>{{ displayValue(format(item.value), 'status') }}</dd></div>
  </dl>
  <div v-else-if="section.type === 'table'" class="analytics-visualization table-visualization">
    <p v-if="section.items?.length" :id="summaryId" :class="!showSummary || businessMode ? 'sr-only' : 'visual-summary'">{{ summaryText }}</p>
    <VisualizationTable v-if="section.items?.length" :section="section" :collapsible="false" :screen-mode="screenMode" :selectable="selectable" @select="item => emit('select', item)" />
    <div v-else class="visual-empty" role="status"><strong>当前条件暂无表格数据</strong><span>请调整或清空当前筛选条件。</span></div>
  </div>
  <div v-else-if="isChartType(section.type)" class="analytics-visualization" :class="{ 'is-compact': compact }">
    <div v-if="!compact && sectionUnit()" class="visual-context"><span class="visual-unit">单位：{{ sectionUnit() }}</span></div>
    <div v-if="!compact && showQuestion && section.visual?.question" class="visual-question">{{ displayText(section.visual.question) }}</div>
    <p :id="summaryId" :class="!showSummary || compact || businessMode ? 'sr-only' : 'visual-summary'">{{ summaryText }}</p>
    <D3SvgChart v-if="section.items?.length" :section="section" :presentation="presentation" :unit="sectionUnit()" :selectable="selectable" @select="item => emit('select', item)" />
    <div v-else class="visual-empty" role="status"><strong>{{ displayText(section.visual?.empty?.title || '当前条件暂无关系数据') }}</strong><span>{{ displayText(section.visual?.empty?.text || '请调整或清空筛选条件。') }}</span></div>
    <VisualizationTable v-if="section.items?.length && showDetails" :section="section" :screen-mode="screenMode" :selectable="selectable" :class="{ 'compact-table-alternative': compact }" @select="item => emit('select', item)" />
  </div>
  <div v-else class="state-panel"><span class="state-symbol">!</span><h2>暂不支持该图表</h2><p>当前数据暂时无法用图表展示，请查看其他分析内容。</p></div>
</template>
