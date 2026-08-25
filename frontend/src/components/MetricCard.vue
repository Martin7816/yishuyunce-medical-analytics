<script setup>
import { displayMetricLabel } from '../domain/displayLabels.js'

const props = defineProps({
  metric: { type: Object, required: true },
  highlighted: Boolean,
  plainNumber: Boolean,
})
const groupedNumber = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false })
const plainNumberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2, useGrouping: false })
function display(metric) {
  if (metric.value == null) return '—'
  if (typeof metric.value !== 'number') return metric.value
  const number = props.plainNumber ? plainNumberFormatter : groupedNumber
  if (metric.unit === '%') return `${number.format(metric.value * 100)}%`
  return number.format(metric.value)
}

function label(metric) {
  return displayMetricLabel(metric)
}
</script>
<template>
  <article class="metric-card" :class="{ highlighted }" :aria-label="`${label(metric)}：${display(metric)}${metric.unit === '%' ? '' : metric.unit || ''}`">
    <p>{{ label(metric) }}</p>
    <div class="metric-value-line">
      <strong>{{ display(metric) }}</strong>
      <small v-if="metric.unit !== '%' && metric.unit">{{ metric.unit }}</small>
    </div>
  </article>
</template>
