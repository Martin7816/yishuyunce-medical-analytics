<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  displaySectionItemValue,
  displayText,
} from '../domain/displayLabels.js'

const props = defineProps({
  section: { type: Object, required: true },
  collapsible: { type: Boolean, default: true },
  screenMode: { type: Boolean, default: false },
  selectable: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false })
const dialogOpen = ref(false)
const dialogPanel = ref(null)
const closeButton = ref(null)
const restoreTarget = ref(null)
const dialogId = `chart-details-dialog-${Math.random().toString(36).slice(2)}`
const dialogTitleId = `${dialogId}-title`
const dialogDescriptionId = `${dialogId}-description`

function isAgeSeverityMatrix() {
  return props.section.key === 'age_severity_matrix'
}

function sectionUnit() {
  if (props.section.visual?.unit || props.section.unit) return props.section.visual?.unit || props.section.unit
  const context = `${props.section.key || ''} ${props.section.title || ''}`
  if (/(收费|成本|金额|费用)/.test(context)) return '美元'
  if (/(住院时长|天数)/.test(context)) return '天'
  if (/(比例|率)/.test(context)) return '%'
  return props.section.type === 'status' ? '' : '条'
}

function formatValue(value, unit) {
  if (value == null) return '—'
  if (typeof value !== 'number') return value
  if (unit === '%') return `${number.format(value * 100)}%`
  return number.format(value)
}

const columns = computed(() => {
  const type = props.section.type
  if (type === 'grouped_bar') return [
    { key: 'category', label: '类别' },
    { key: 'series_label', label: '系列' },
    { key: 'value', label: displayText(props.section.visual?.y_label || '数值') },
    { key: 'unit', label: '单位' },
  ]
  if (type === 'scatter') {
    const labels = {
      name: '分组', x: displayText(props.section.visual?.x_label || '横轴指标'), y: displayText(props.section.visual?.y_label || '纵轴指标'),
      cost: '平均成本（美元）', size: '记录数（条）', group: displayText(props.section.visual?.legend?.[0]?.label || '分组'), high_cost_rate: '高费用率',
    }
    const fallback = props.section.visual?.fallback?.columns || Object.keys(labels)
    return fallback.map(key => ({ key, label: labels[key] || key }))
  }
  if (type === 'correlation') return [
    { key: 'x_label', label: '指标一' },
    { key: 'y_label', label: '指标二' },
    { key: 'coefficient', label: '相关系数' },
    { key: 'sample_size', label: '有效记录数' },
    { key: 'method', label: '计算方法' },
  ]
  if (type === 'heatmap') {
    const heatmapColumns = [
      { key: 'x_label', label: displayText(props.section.visual?.x_label || '横轴分类') },
      { key: 'y_label', label: displayText(props.section.visual?.y_label || '纵轴分类') },
      { key: 'value', label: isAgeSeverityMatrix() ? '病例量' : '值' },
      { key: 'unit', label: '单位' },
    ]
    if (isAgeSeverityMatrix()) heatmapColumns.push({ key: 'age_group_share', label: '年龄组内占比' })
    else heatmapColumns.push(
      { key: 'numerator', label: '分子' },
      { key: 'denominator', label: '分母' },
      { key: 'high_risk_rate', label: '重症/极重症比例' },
    )
    return heatmapColumns.filter(column => column.key === 'age_group_share' || props.section.items.some(item => item[column.key] != null))
  }
  return [{ key: 'name', label: '类别' }, { key: 'value', label: displayText(props.section.visual?.y_label || '数值') }, { key: 'unit', label: '单位' }]
})

const rows = computed(() => props.section.type === 'grouped_bar'
  ? props.section.items.flatMap(item => item.series.map(series => ({ category: item.category, series_label: series.label, value: series.value, unit: props.section.visual?.unit || '—' })))
  : props.section.items)

const ageGroupTotals = computed(() => {
  const totals = new Map()
  if (!isAgeSeverityMatrix()) return totals
  for (const row of rows.value) {
    if (typeof row.value !== 'number' || row.x_label == null) continue
    totals.set(row.x_label, (totals.get(row.x_label) || 0) + row.value)
  }
  return totals
})

const ageSeverityGroups = computed(() => {
  if (!isAgeSeverityMatrix()) return []
  const groups = []
  const groupsByLabel = new Map()
  for (const row of rows.value) {
    const key = row.x_label
    let group = groupsByLabel.get(key)
    if (!group) {
      group = { key, rows: [] }
      groupsByLabel.set(key, group)
      groups.push(group)
    }
    group.rows.push(row)
  }
  return groups
})

const ageSeverityColumns = computed(() => columns.value.filter(column => column.key !== 'x_label'))

function ageGroupShare(row) {
  const total = ageGroupTotals.value.get(row.x_label) || 0
  return total > 0 && typeof row.value === 'number' ? row.value / total : 0
}

function detailDescription() {
  return isAgeSeverityMatrix()
    ? '病例量及年龄组内占比；占比按该年龄组全部严重程度病例量计算。'
    : '精确数值和单位。'
}

function openDetails() {
  if (dialogOpen.value || typeof document === 'undefined') return
  restoreTarget.value = document.activeElement
  dialogOpen.value = true
}

function closeDetails() {
  if (!dialogOpen.value) return
  const target = restoreTarget.value
  restoreTarget.value = null
  dialogOpen.value = false
  nextTick(() => {
    if (target && typeof target.focus === 'function' && document.contains(target)) target.focus({ preventScroll: true })
  })
}

function focusableDialogElements() {
  return Array.from(dialogPanel.value?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') || [])
    .filter(element => !element.disabled && element.getAttribute('aria-hidden') !== 'true')
}

function handleDialogKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDetails()
    return
  }
  if (event.key !== 'Tab') return

  const elements = focusableDialogElements()
  if (!elements.length) return
  const first = elements[0]
  const last = elements[elements.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function selectRow(row) {
  if (dialogOpen.value) closeDetails()
  emit('select', row)
}

function syncModalBodyState() {
  if (typeof document === 'undefined') return
  document.body.classList.toggle('chart-details-modal-open', dialogOpen.value)
  document.body.classList.toggle('chart-details-modal-screen', dialogOpen.value && props.screenMode)
}

watch([dialogOpen, () => props.screenMode], () => {
  syncModalBodyState()
  if (dialogOpen.value) nextTick(() => closeButton.value?.focus({ preventScroll: true }))
})

onBeforeUnmount(() => {
  if (typeof document === 'undefined') return
  document.body.classList.remove('chart-details-modal-open', 'chart-details-modal-screen')
})

function display(row, key) {
  if (key === 'unit') return row.unit || sectionUnit() || '—'
  if (key === 'age_group_share') return formatValue(ageGroupShare(row), '%')
  if (key === 'coefficient') return typeof row[key] === 'number' ? row[key].toFixed(4) : '—'
  if (['name', 'category', 'series_label', 'x_label', 'y_label', 'group'].includes(key)) {
    return displaySectionItemValue(row[key], props.section, key) || '—'
  }
  if (key === 'method') return displayText(row[key]) || '—'
  const unit = key === 'high_cost_rate' || key === 'high_risk_rate' ? '%'
    : key === 'x' ? '天'
      : key === 'y' || key === 'cost' ? '美元'
        : key === 'size' || key === 'numerator' || key === 'denominator' ? '条'
          : key === 'sample_size' ? '条'
          : key === 'value' ? row.unit || sectionUnit() : undefined
  return formatValue(row[key], unit)
}
</script>

<template>
  <div v-if="collapsible && rows.length" class="chart-alternative chart-details-trigger">
    <button type="button" class="chart-details-summary" :aria-controls="dialogId" :aria-expanded="dialogOpen" aria-haspopup="dialog" @click="openDetails">
      <span class="chart-details-title">查看数据明细</span>
      <span class="chart-details-disclosure" aria-hidden="true">+</span>
    </button>
    <Teleport to="body">
      <div v-if="dialogOpen" class="chart-details-modal" @click.self="closeDetails" @keydown="handleDialogKeydown">
        <section :id="dialogId" ref="dialogPanel" class="chart-details-dialog" role="dialog" aria-modal="true" :aria-labelledby="dialogTitleId" :aria-describedby="dialogDescriptionId">
          <header class="chart-details-dialog-header">
            <div>
              <p class="chart-details-dialog-eyebrow">数据明细</p>
              <h2 :id="dialogTitleId">{{ displayText(section.title) }}</h2>
              <p :id="dialogDescriptionId" class="chart-details-dialog-description">{{ detailDescription() }}</p>
            </div>
            <button ref="closeButton" type="button" class="chart-details-dialog-close" aria-label="关闭数据明细" @click="closeDetails">
              <span aria-hidden="true">×</span>
            </button>
          </header>
          <div class="chart-details-body">
            <div class="table-scroll">
              <table class="analytics-data-table">
                <caption>{{ displayText(section.title) }}数据明细。</caption>
                <thead><tr><th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
                <tbody>
                  <template v-if="isAgeSeverityMatrix()">
                    <template v-for="group in ageSeverityGroups" :key="`${section.key}-dialog-group-${group.key}`">
                      <tr v-for="(row, rowIndex) in group.rows" :key="`${section.key}-dialog-row-${group.key}-${rowIndex}`" :class="{ 'analytics-table-group-start': rowIndex === 0 }">
                        <th v-if="rowIndex === 0" class="analytics-table-group-label" scope="rowgroup" :rowspan="group.rows.length">
                          <button v-if="selectable" type="button" class="table-drilldown-button" @click="selectRow(group.rows[0])">{{ display(group.rows[0], 'x_label') }}</button>
                          <template v-else>{{ display(group.rows[0], 'x_label') }}</template>
                        </th>
                        <td v-for="column in ageSeverityColumns" :key="column.key">{{ display(row, column.key) }}</td>
                      </tr>
                    </template>
                  </template>
                  <tr v-else v-for="(row, rowIndex) in rows" :key="`${section.key}-dialog-row-${rowIndex}`">
                    <td v-for="(column, columnIndex) in columns" :key="column.key">
                      <button v-if="selectable && columnIndex === 0" type="button" class="table-drilldown-button" @click="selectRow(row)">{{ display(row, column.key) }}</button>
                      <template v-else>{{ display(row, column.key) }}</template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
  <details v-else-if="rows.length" class="chart-alternative" open>
    <h3 class="chart-alternative-title">数据表</h3>
    <div class="chart-details-body">
      <p class="chart-details-description">{{ displayText(section.title) }}：{{ detailDescription() }}</p>
      <div class="table-scroll">
        <table class="analytics-data-table">
          <caption>{{ displayText(section.title) }}数据明细。</caption>
          <thead><tr><th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
          <tbody>
            <template v-if="isAgeSeverityMatrix()">
              <template v-for="group in ageSeverityGroups" :key="`${section.key}-group-${group.key}`">
                <tr v-for="(row, rowIndex) in group.rows" :key="`${section.key}-row-${group.key}-${rowIndex}`" :class="{ 'analytics-table-group-start': rowIndex === 0 }">
                  <th v-if="rowIndex === 0" class="analytics-table-group-label" scope="rowgroup" :rowspan="group.rows.length">
                    <button v-if="selectable" type="button" class="table-drilldown-button" @click="selectRow(group.rows[0])">{{ display(group.rows[0], 'x_label') }}</button>
                    <template v-else>{{ display(group.rows[0], 'x_label') }}</template>
                  </th>
                  <td v-for="column in ageSeverityColumns" :key="column.key">{{ display(row, column.key) }}</td>
                </tr>
              </template>
            </template>
            <tr v-else v-for="(row, rowIndex) in rows" :key="`${section.key}-row-${rowIndex}`">
              <td v-for="(column, columnIndex) in columns" :key="column.key">
                <button v-if="selectable && columnIndex === 0" type="button" class="table-drilldown-button" @click="selectRow(row)">{{ display(row, column.key) }}</button>
                <template v-else>{{ display(row, column.key) }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </details>
</template>
