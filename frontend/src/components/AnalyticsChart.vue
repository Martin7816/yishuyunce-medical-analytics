<script setup>
import { computed } from 'vue'
import { d3ChartTypes, resolveChartPresentation } from '../domain/chartPresentation.js'
import D3SvgChart from './D3SvgChart.vue'
import VisualizationTable from './VisualizationTable.vue'

const props = defineProps({
  section: { type: Object, required: true },
  compact: { type: Boolean, default: false },
  showQuestion: { type: Boolean, default: true },
  businessMode: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])
const listTypes = new Set(['status'])
const summaryId = `chart-summary-${Math.random().toString(36).slice(2)}`
const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })

const presentation = computed(() => resolveChartPresentation(props.section))

function format(value) {
  if (value == null) return '—'
  return typeof value === 'number' ? numberFormat.format(value) : value
}

function itemLabel(item) {
  return item.name || item.category || item.x_label || item.y_label || '该分组'
}

function sectionUnit() {
  if (props.section.visual?.unit || props.section.unit) return props.section.visual?.unit || props.section.unit
  const context = `${props.section.key || ''} ${props.section.title || ''}`
  if (/(收费|成本|金额|费用)/.test(context)) return '美元'
  if (/(住院时长|天数)/.test(context)) return '天'
  if (/(比例|率)/.test(context)) return '%'
  return props.section.type === 'status' ? '' : '条'
}

function ageLabel(value) {
  return {
    '0 to 17': '0-17岁',
    '18 to 29': '18-29岁',
    '30 to 49': '30-49岁',
    '50 to 69': '50-69岁',
    '70 or Older': '70岁及以上',
  }[value] || value
}

function scatterSummary(items) {
  const points = items.filter(item => typeof item.y === 'number')
  if (!points.length) return '当前没有可展示的业务结果。'
  const top = points.reduce((current, item) => item.y > current.y ? item : current, points[0])
  const group = top.group ? `${top.group}组` : itemLabel(top)
  return `${group}的平均收费最高，为${format(top.y)}${sectionUnit()}；可结合住院时长、成本和高费用率比较差异。`
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
  return `${ageLabel(topAge)}组的Major/Extreme记录占比最高，约${rate}%；可结合病例量进一步分析。`
}

function businessSummary() {
  if (!props.businessMode && props.section.visual?.summary?.text) return props.section.visual.summary.text

  if (props.businessMode && presentation.value === 'scatter') return scatterSummary(props.section.items || [])
  if (props.businessMode && presentation.value === 'heatmap') return heatmapSummary(props.section.items || [])

  const items = (props.section.items || []).filter(item => typeof item.value === 'number')
  if (!items.length) return '当前没有可展示的业务结果。'

  const top = items.reduce((current, item) => item.value > current.value ? item : current, items[0])
  if (presentation.value === 'pie') {
    const total = items.reduce((sum, item) => sum + item.value, 0)
    const share = total > 0 ? numberFormat.format((top.value / total) * 100) : null
    return share == null
      ? `${props.section.title || '当前结构'}已按分组汇总，详细数值见下方数据表。`
      : `${props.section.title || '当前结构'}中，${itemLabel(top)}占比最高，约${share}%。`
  }

  if (props.section.visual?.summary?.text) return props.section.visual.summary.text

  const unit = sectionUnit()
  const valueLabel = unit === '条' ? '病例量' : '数值'
  return `${props.section.title || '当前分析'}中，${itemLabel(top)}${valueLabel}最多，共${format(top.value)}${unit}。`
}

const summaryText = computed(businessSummary)

function isChartType(type) { return d3ChartTypes.has(type) }
</script>

<template>
  <dl v-if="listTypes.has(section.type)" class="status-grid" :aria-label="section.title">
    <div v-for="item in section.items" :key="item.name"><dt>{{ item.name }}</dt><dd>{{ format(item.value) }}</dd></div>
  </dl>
  <div v-else-if="section.type === 'table'" class="analytics-visualization table-visualization">
    <p v-if="section.items?.length" :id="summaryId" class="visual-summary">{{ summaryText }}</p>
    <VisualizationTable v-if="section.items?.length" :section="section" :collapsible="false" @select="item => emit('select', item)" />
    <div v-else class="visual-empty" role="status"><strong>当前条件暂无表格数据</strong><span>请调整或清空已发布筛选。</span></div>
  </div>
  <div v-else-if="isChartType(section.type)" class="analytics-visualization" :class="{ 'is-compact': compact }">
    <div v-if="!compact && sectionUnit()" class="visual-context"><span class="visual-unit">单位：{{ sectionUnit() }}</span></div>
    <div v-if="!compact && showQuestion && section.visual?.question" class="visual-question">{{ section.visual.question }}</div>
    <p :id="summaryId" :class="compact ? 'sr-only' : 'visual-summary'">{{ summaryText }}</p>
    <D3SvgChart v-if="section.items?.length" :section="section" :presentation="presentation" :unit="sectionUnit()" @select="item => emit('select', item)" />
    <div v-else class="visual-empty" role="status"><strong>{{ section.visual?.empty?.title || '当前条件暂无关系数据' }}</strong><span>{{ section.visual?.empty?.text || '请调整或清空筛选条件。' }}</span></div>
    <p v-if="!compact && section.visual?.summary?.related_not_causal" class="related-note">相关不等于因果；结果来自住院出院记录的汇总统计。</p>
    <VisualizationTable v-if="section.items?.length" :section="section" :class="{ 'compact-table-alternative': compact }" @select="item => emit('select', item)" />
  </div>
  <div v-else class="state-panel"><span class="state-symbol">!</span><h2>暂不支持该图表</h2><p>当前数据暂时无法用图表展示，请查看其他分析内容。</p></div>
</template>
