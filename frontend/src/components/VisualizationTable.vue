<script setup>
import { computed } from 'vue'

const props = defineProps({
  section: { type: Object, required: true },
  collapsible: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })

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
    { key: 'value', label: props.section.visual?.y_label || '数值' },
    { key: 'unit', label: '单位' },
  ]
  if (type === 'scatter') {
    const labels = {
      name: '分组', x: props.section.visual?.x_label || 'X 值', y: props.section.visual?.y_label || 'Y 值',
      cost: '平均成本（美元）', size: '记录数（条）', group: props.section.visual?.legend?.[0]?.label || '分组', high_cost_rate: '高费用率',
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
  if (type === 'heatmap') return [
    { key: 'x_label', label: props.section.visual?.x_label || '横轴分类' },
    { key: 'y_label', label: props.section.visual?.y_label || '纵轴分类' },
    { key: 'value', label: '值' }, { key: 'unit', label: '单位' },
    { key: 'numerator', label: '分子' }, { key: 'denominator', label: '分母' }, { key: 'high_risk_rate', label: 'Major/Extreme 比例' },
  ].filter(column => props.section.items.some(item => item[column.key] != null))
  return [{ key: 'name', label: '类别' }, { key: 'value', label: props.section.visual?.y_label || '数值' }, { key: 'unit', label: '单位' }]
})

const rows = computed(() => props.section.type === 'grouped_bar'
  ? props.section.items.flatMap(item => item.series.map(series => ({ category: item.category, series_label: series.label, value: series.value, unit: props.section.visual?.unit || '—' })))
  : props.section.items)

function display(row, key) {
  if (key === 'unit') return row.unit || sectionUnit() || '—'
  if (key === 'coefficient') return typeof row[key] === 'number' ? row[key].toFixed(4) : '—'
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
  <details v-if="rows.length" class="chart-alternative" :open="!collapsible">
    <summary v-if="collapsible" class="chart-details-summary">
      <span class="chart-details-title">查看数据明细</span>
      <span class="chart-details-note">查看精确数值</span>
    </summary>
    <h3 v-else class="chart-alternative-title">数据表</h3>
    <div class="chart-details-body">
      <p class="chart-details-description">{{ section.title }}的精确数值和单位。</p>
      <div class="table-scroll">
        <table class="analytics-data-table">
          <caption>{{ section.title }}数据明细。</caption>
          <thead><tr><th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, rowIndex) in rows" :key="`${section.key}-row-${rowIndex}`">
              <td v-for="(column, columnIndex) in columns" :key="column.key">
                <button v-if="columnIndex === 0" type="button" class="table-drilldown-button" @click="emit('select', row)">{{ display(row, column.key) }}</button>
                <template v-else>{{ display(row, column.key) }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </details>
</template>
