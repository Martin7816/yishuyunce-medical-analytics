<script setup>
defineProps({ metric: { type: Object, required: true } })
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
function display(metric) {
  if (typeof metric.value !== 'number') return metric.value
  if (metric.unit === '%') return `${number.format(metric.value * 100)}%`
  return number.format(metric.value)
}
</script>
<template><article class="metric-card"><p>{{ metric.label }}</p><strong>{{ display(metric) }}</strong><small v-if="metric.unit !== '%'">{{ metric.unit }}</small></article></template>
